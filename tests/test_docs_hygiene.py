"""Documentation folder hygiene tests."""

import json
import re
from pathlib import Path

from ai4binance.governance.repository_validator import DKG_CORE_REQUIRED_SECTION_TITLES
from tests.documentation_hygiene_helpers import (
    STALE_KNOWLEDGE_TEMPLATE_REFERENCE,
    documentation_markdown_files,
    is_excluded_documentation_analysis_path,
    stale_knowledge_template_offenders,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
AGENTS = ROOT / "AGENTS.md"
OPERATIONS_REPORTS = ROOT / "runtime" / "reports" / "operations"
CORE_VNEXT_FRAMEWORK = DOCS / "governance/framework_core_vnext_governance.md"
CUSTOM_INSTRUCTIONS = DOCS / "governance" / "instruction_core_custom_instructions.md"
CODEX_PROVIDER_INSTRUCTIONS = DOCS / "providers" / "instruction_codex_provider.md"
CLAUDE_PROVIDER_INSTRUCTIONS = DOCS / "providers" / "instruction_claude_provider.md"
COMPLIANCE_MATRIX = DOCS / "compliance/registry_compliance_matrix.md"
REPOSITORY_FILE_GOVERNANCE_STANDARD = (
    DOCS / "standards" / "standard_repository_file_governance.md"
)
REPOSITORY_STRUCTURE_GOVERNANCE_STANDARD = (
    DOCS / "standards" / "standard_repository_structure_governance.md"
)
REPOSITORY_ARTIFACT_SEPARATION_STANDARD = (
    DOCS / "standards" / "standard_repository_artifact_separation_governance.md"
)
REPOSITORY_VALIDATOR_GOVERNANCE_STANDARD = (
    DOCS / "standards" / "standard_repository_validator_governance.md"
)
DOCUMENTATION_KNOWLEDGE_GOVERNANCE_STANDARD = (
    DOCS / "standards" / "standard_documentation_knowledge_governance.md"
)
QUALITY_GATE_PROFILE_RUNBOOK = DOCS / "workflows" / "runbook_quality_gate_profiles.md"
WORKFLOW_REGISTRY = DOCS / "registries" / "registry_workflow_registry.md"


def test_repository_artifact_reference_embedded_schema_matches_machine_schema() -> None:
    reference_text = (
        DOCS / "schemas" / "reference_repository_artifact_schema.md"
    ).read_text(encoding="utf-8")
    machine_schema = json.loads(
        (ROOT / "schemas" / "governance" / "repository_artifact.schema.json").read_text(
            encoding="utf-8"
        )
    )

    for field in ("lifecycle_status", "authority_layer", "authority_effect"):
        match = re.search(
            rf'"{field}":\s*\{{.*?"enum":\s*(\[[^\]]*\])',
            reference_text,
            re.DOTALL,
        )
        assert match is not None, f"Reference schema document must define {field}."
        assert json.loads(match.group(1)) == machine_schema["properties"][field]["enum"]

    required_match = re.search(
        r'"required":\s*(\[[^\]]*\])',
        reference_text,
        re.DOTALL,
    )
    assert required_match is not None
    required_fields = set(json.loads(required_match.group(1)))
    assert {
        "source_of_truth",
        "machine_enforceable",
        "audit_required",
        "classification",
    }.issubset(required_fields)

    for field, expected_type in (
        ("source_of_truth", "boolean"),
        ("machine_enforceable", "boolean"),
        ("audit_required", "boolean"),
    ):
        match = re.search(
            rf'"{field}":\s*\{{\s*"type":\s*"([^"]+)"',
            reference_text,
            re.DOTALL,
        )
        assert match is not None, f"Reference schema document must define {field}."
        assert match.group(1) == expected_type


TEMPORARY_OPERATION_PATTERNS = (
    "*_DIFF_PLAN_*.md",
    "*_IMPLEMENTATION_PLAN.md",
    "*_IMPLEMENTATION_REPORT.md",
    "*_WATCHLIST_*.md",
    "*_DRAFT_QUEUE.md",
)


EXPECTED_OPERATION_REPORTS = {
    "COVERAGE_DIFF_PLAN_20260719.md",
    "DOCS_INFORMATION_ARCHITECTURE_DIFF_PLAN_20260829.md",
    "DYNAMIC_PORTFOLIO_IMPLEMENTATION_PLAN.md",
    "EVIDENCE_BACKED_X_DRAFT_QUEUE.md",
    "EXTERNAL_RESEARCH_WATCHLIST_20260716.md",
    "OPENBB_FREQTRADE_STRENGTHENING.md",
    "REPO_CLEANUP_DIFF_PLAN_20260728.md",
    "REPOSITORY_CLEANUP_RF_IMPLEMENTATION_REPORT.md",
    "WORKTREE_DIFF_PLAN_20260719.md",
}

CANONICAL_DOCS_ROOT_DIRECTORIES = {
    "governance",
    "architecture",
    "standards",
    "policies",
    "controls",
    "contracts",
    "registries",
    "ontology",
    "workflows",
    "compliance",
    "security",
    "assurance",
    "runbooks",
    "adr",
    "references",
}

CANONICAL_GOVERNANCE_DIRECTORIES = {
    "constitution",
    "authority",
    "decision",
    "execution",
    "promotion",
    "repository",
}

CANONICAL_ARCHITECTURE_DIRECTORIES = {
    "system",
    "data",
    "decision",
    "runtime",
    "integration",
}


def test_draft_reports_are_excluded_from_analysis_scope() -> None:
    assert is_excluded_documentation_analysis_path(
        ROOT, ROOT / "runtime" / "reports" / "draft_docs" / "local-draft.md"
    )
    assert not is_excluded_documentation_analysis_path(
        ROOT, ROOT / "runtime" / "reports" / "operations" / "SYSTEM_REPORT.md"
    )


def test_docs_contains_no_temporary_operation_documents() -> None:
    offenders = sorted(
        path.relative_to(ROOT).as_posix()
        for pattern in TEMPORARY_OPERATION_PATTERNS
        for path in DOCS.glob(pattern)
    )

    assert offenders == []


def test_operation_reports_are_separated_from_permanent_docs() -> None:
    reports = {
        path.name
        for path in OPERATIONS_REPORTS.glob("*.md")
        if path.name != "README.md"
    }

    assert EXPECTED_OPERATION_REPORTS <= reports


def test_canonical_docs_information_architecture_directories_exist() -> None:
    root_directories = {path.name for path in DOCS.iterdir() if path.is_dir()}
    governance_directories = {
        path.name for path in (DOCS / "governance").iterdir() if path.is_dir()
    }
    architecture_directories = {
        path.name for path in (DOCS / "architecture").iterdir() if path.is_dir()
    }

    assert CANONICAL_DOCS_ROOT_DIRECTORIES <= root_directories
    assert CANONICAL_GOVERNANCE_DIRECTORIES <= governance_directories
    assert CANONICAL_ARCHITECTURE_DIRECTORIES <= architecture_directories


def test_docs_and_reports_have_eli10_explanations() -> None:
    markdown_files = [
        path
        for path in documentation_markdown_files(ROOT)
        if not is_excluded_documentation_analysis_path(ROOT, path)
    ]

    missing = [
        path.relative_to(ROOT).as_posix()
        for path in markdown_files
        if "\n## ELI10\n" not in path.read_text(encoding="utf-8")
    ]

    assert missing == []

    duplicated = [
        path.relative_to(ROOT).as_posix()
        for path in markdown_files
        if path.read_text(encoding="utf-8").count("\n## ELI10\n") != 1
    ]

    assert duplicated == []


def test_canonical_docs_markdown_filenames_and_metadata_are_classified() -> None:
    pattern = re.compile(
        r"^(?:[a-z]+(?:_[a-z]+)?)_[a-z0-9]+(?:_[a-z0-9]+)*_[a-z0-9]+(?:_[a-z0-9]+)*\.md$"
    )
    docs_index_exceptions = {"docs/README.md"}
    required_frontmatter_keys = {
        "document_type",
        "authority_level",
        "content_role",
        "source_of_truth",
        "canonical_path",
    }
    offenders: list[str] = []

    for path in DOCS.rglob("*.md"):
        relative = path.relative_to(ROOT).as_posix()
        if relative in docs_index_exceptions:
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        has_frontmatter = len(lines) >= 3 and lines[0].strip() == "---"
        metadata: dict[str, str] = {}
        if has_frontmatter:
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                if ": " in line:
                    key, value = line.split(": ", 1)
                    metadata[key.strip()] = value.strip()
        missing_keys = sorted(required_frontmatter_keys - metadata.keys())
        if not pattern.match(path.name) or not has_frontmatter or missing_keys:
            detail = []
            if not pattern.match(path.name):
                detail.append("filename")
            if not has_frontmatter:
                detail.append("frontmatter")
            if missing_keys:
                detail.append("metadata=" + ",".join(missing_keys))
            offenders.append(f"{relative} [{' ; '.join(detail)}]")

    assert offenders == []


def test_documentation_knowledge_standard_preserves_full_source_section_contract() -> (
    None
):
    text = DOCUMENTATION_KNOWLEDGE_GOVERNANCE_STANDARD.read_text(encoding="utf-8")
    missing = [
        title
        for title in DKG_CORE_REQUIRED_SECTION_TITLES
        if f"## {title}" not in text
        and not any(
            line.startswith("## ") and line.endswith(title)
            for line in text.splitlines()
        )
    ]

    assert len(DKG_CORE_REQUIRED_SECTION_TITLES) == 13
    assert missing == []


def test_documentation_knowledge_split_lineage_uses_canonical_template_path() -> None:
    expected_files = (
        DOCUMENTATION_KNOWLEDGE_GOVERNANCE_STANDARD,
        DOCS / "templates" / "reference_governed_knowledge_object_template.md",
        ROOT
        / "docs"
        / "reports"
        / "report_documentation_knowledge_governance_split_manifest.md",
        DOCS / "references" / "reference_governed_knowledge_taxonomy.md",
        DOCS / "registries" / "registry_documentation_index.md",
    )

    for path in expected_files:
        text = path.read_text(encoding="utf-8")
        assert STALE_KNOWLEDGE_TEMPLATE_REFERENCE not in text

    canonical_template_path = (
        "docs/templates/reference_governed_knowledge_object_template.md"
    )
    assert canonical_template_path in (
        ROOT
        / "docs"
        / "reports"
        / "report_documentation_knowledge_governance_split_manifest.md"
    ).read_text(encoding="utf-8")
    assert canonical_template_path in (
        DOCS / "references" / "reference_governed_knowledge_taxonomy.md"
    ).read_text(encoding="utf-8")
    assert canonical_template_path in (
        DOCS / "registries" / "registry_documentation_index.md"
    ).read_text(encoding="utf-8")


def test_documentation_markdown_does_not_reference_stale_knowledge_template_path() -> (
    None
):
    assert stale_knowledge_template_offenders(ROOT) == []


def test_quality_gate_profile_runbook_links_active_machine_policy() -> None:
    runbook_text = QUALITY_GATE_PROFILE_RUNBOOK.read_text(encoding="utf-8")
    workflow_registry_text = WORKFLOW_REGISTRY.read_text(encoding="utf-8")
    quality_config_text = (ROOT / "config" / "quality" / "gates.yaml").read_text(
        encoding="utf-8"
    )
    quality_script_text = (ROOT / "scripts" / "quality.ps1").read_text(encoding="utf-8")

    required_runbook_fragments = (
        "status: ACTIVE",
        "authority_scope: quality_gate_profile_workflow",
        "config/quality/gates.yaml",
        "scripts/quality.ps1",
        "docs/registries/registry_workflow_registry.md",
        "runtime/quality/",
        "runtime/artifacts/quality/gate/",
        "FAST_VERIFIED",
        "STANDARD_VERIFIED",
        "FULL_VERIFIED",
        "NO_MYPY_PLUS_DMYPY_DUPLICATION",
        "FAIL_CLOSED_TEST_SELECTION",
        "NO_SILENT_TEST_SKIPPING",
        "NO_FALSE_FULL_VERIFICATION",
        "## Pytest Scope Model",
        "## Affected-Test Mapping Rules",
        "## Critical Escalation Rules",
        "## Console Output Rules",
        (
            "`profile`,\n`run_id`, `status`, `duration`, `tools`, "
            "`selected_test_count`, and"
        ),
        "`failed_step`,\n`exit_code`, `first_actionable_error`, and `evidence_path`",
        "runtime/artifacts/quality/gate/runs/<run_id>/<step_id>-output.txt",
        "## Timing And Baseline Rules",
        "RESEARCH_ONLY",
        "NO_TRADE",
        "LIVE_ORDER_BLOCKED",
    )
    for fragment in required_runbook_fragments:
        assert fragment in runbook_text

    assert "type_check: dmypy" in quality_config_text
    assert "pytest_scope: affected" in quality_config_text
    assert "unknown_impact_escalates_to: standard" in quality_config_text
    assert "dmypy_is_local_accelerator_only: true" in quality_config_text
    assert "evidence_root: runtime/quality" in quality_config_text
    assert "compatibility_evidence_root: runtime/artifacts/quality/gate" in (
        quality_config_text
    )
    assert '[ValidateSet("fast", "standard", "full")]' in quality_script_text
    assert 'full_verification_status = "NOT_VERIFIED"' in quality_script_text
    assert 'verification_status = "FULL_VERIFIED"' in quality_script_text
    assert "QG-PROFILE-001" in workflow_registry_text
    assert "docs/workflows/runbook_quality_gate_profiles.md" in (workflow_registry_text)
    assert "runtime/quality/latest.json" in workflow_registry_text


def test_core_constitution_change_control_is_synced_across_written_rules() -> None:
    expected_by_document = {
        CORE_VNEXT_FRAMEWORK: (
            "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
            "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
            "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
            (
                "Risk-tiered human governance applies only when the proven "
                "change is consequential."
            ),
            "Approval Packet",
            "scope_hash",
            "Code/constitution divergence is prohibited.",
            "Cleanup audit registry evidence rule",
            "source, test, compliance matrix and core doc",
            "full quality_gate evidence",
            "Coverage and pass counts must come from the full quality gate evidence",
            "Wide-scope audit rule",
            "local CPU/RAM/GPU capacity",
            "honest cover rate",
            "Constitution family mismatch visibility rule",
            "core, Custom Instructions, Codex and compliance matrix",
            "Loose changed source rule",
            "Capability OOS/operational evidence gap rule",
            "Capability OOS/operational evidence gaps remain visible",
            "artifact-level OOS",
            "Every gap remains visibly",
            "Repository governance enforcement rule",
            "RepositoryPolicy",
            "RepositoryArtifact schema",
            "deterministic repository_validator",
            "Documentation and knowledge governance rule",
            "GovernedKnowledgeObject",
            "AI4B-GOV-DKG-001",
            "Duplicate active source-of-truth concepts",
            "Docs are authority.",
            "Validator is enforcement.",
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "Runtime is not source-of-truth.",
            "LLM is not authority.",
            "Scores cannot hide blockers.",
            "LIVE remains blocked.",
            "RUNTIME/ GROUPS MUTABLE, GENERATED, REPRODUCIBLE,",
            "AND EXECUTION/RUN-PRODUCED OUTPUTS",
            "IF DELETING A FILE WOULD MAKE THE REPOSITORY UNDEFINED,",
            "IT DOES NOT BELONG UNDER RUNTIME/",
            "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
            "LIVE_ORDER_BLOCKED",
        ),
        CUSTOM_INSTRUCTIONS: (
            "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
            "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
            "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
            (
                "Risk-tiered human governance applies only when the proven "
                "change is consequential."
            ),
            "Approval Packet",
            "scope_hash",
            "Code and written constitution must not diverge.",
            "Legacy document modernization rule",
            "Cleanup audit registry evidence rule",
            "source, test, compliance",
            "Transparent proof rule",
            "Wide-scope audit rule",
            "CPU/RAM/GPU",
            "cover rate",
            "Constitution family mismatch visibility rule",
            "Loose changed source rule",
            "Capability OOS/operational evidence gap rule",
            "Repository governance enforcement rule",
            "RepositoryPolicy + RepositoryArtifact schema",
            "deterministic repository_validator",
            "Documentation and knowledge governance rule",
            "GovernedKnowledgeObject",
            "AI4B-GOV-DKG-001",
            "Duplicate active source-of-truth",
            "Docs are authority.",
            "Validator is enforcement.",
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "Runtime is not source-of-truth.",
            "LLM is not authority.",
            "Scores cannot hide blockers.",
            "LIVE remains blocked.",
            "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
            "LIVE_ORDER_BLOCKED",
        ),
        CODEX_PROVIDER_INSTRUCTIONS: (
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
        ),
        COMPLIANCE_MATRIX: (
            "Constitutional change control",
            "Governance alignment / loose-code audit",
            "TECHNICAL_TRUTH",
            "POLICY_ELIGIBILITY",
            "CONSEQUENTIAL_AUTHORITY",
            "risk-tiered human governance",
            "ELI10",
            "relevant policy/instructions",
            "pytest_pass_count",
            "coverage_percent",
            "source, test, compliance matrix, and core documentation evidence",
            "CPU/RAM/GPU",
            "coverage rate cannot be inferred from outside full quality_gate evidence",
            "core/root/custom/codex/compliance",
            "empty-source-file change",
            "Capability OOS/operational evidence gap",
            "Repository & File Governance Standard",
            "RepositoryPolicy + RepositoryArtifact schema",
            "repository_validator",
            "Documentation & Knowledge Governance Standard",
            "GovernedKnowledgeObject",
            "AI4B-GOV-DKG-001",
            "duplicate active source-of-truth concept",
            "Docs are authority.",
            "Validator is enforcement.",
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "Runtime is not source-of-truth.",
            "LLM is not authority.",
            "Scores cannot hide blockers.",
            "LIVE remains blocked.",
            "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
            "LIVE_ORDER_BLOCKED",
        ),
        DOCS / "governance" / "framework_decision_governance_engine.md": (
            "Opportunity lifecycle states such as `WATCH_ONLY` and "
            "`CONFIRMATION_PENDING`",
            "No score may compensate for an active hard blocker.",
            "promotion_status = RESEARCH_ONLY",
            "live_eligibility_status = LIVE_ORDER_BLOCKED",
        ),
        DOCS / "governance" / "policy_organization_market_strategy_validation.md": (
            "Opportunity lifecycle labels such as `WATCH_ONLY`, "
            "`CONFIRMATION_PENDING`,",
            "Strategy promotion remains governed by research, backtest, walk-forward,",
            "out-of-sample, robustness, paper, and human approval gates.",
        ),
        DOCS / "registries" / "registry_strategy_registry.md": (
            "Strategy family expansion is therefore governed by the same staged ",
            "evidence",
            "chain: research, backtest, walk-forward, out-of-sample, robustness, ",
            "paper, and",
            "they do not grant trade authority by themselves.",
        ),
        REPOSITORY_FILE_GOVERNANCE_STANDARD: (
            "AI4B-GOV-REPO-001",
            "RepositoryArtifact Schema",
            "repository_validator.py",
            "quality gate",
            "RUNNING_WITH_BLOCKERS",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
        ),
        REPOSITORY_STRUCTURE_GOVERNANCE_STANDARD: (
            "Within L8, `runtime/` is the canonical grouping root for mutable, "
            "generated,",
            "reproducible, and execution/run-produced outputs.",
            "into the appropriate governed subtree under `runtime/` rather than spread",
            "Repository root describes the system;",
            "`runtime/` describes what the system",
            "produces while operating. If deleting a file would make the repository",
            "undefined or remove governed authority, that file must live outside",
            "`runtime/` and under the governed source, policy, schema,",
            "registry, or docs",
            "surface that owns it.",
        ),
        REPOSITORY_ARTIFACT_SEPARATION_STANDARD: (
            "runtime/    = local execution workspace; canonical grouping root for "
            "mutable,",
            "generated, reproducible, and execution/run-produced outputs",
            "runtime/artifacts/  = machine-readable generated evidence",
            "runtime/reports/    = human-readable runtime summaries",
            "runtime/state/      = mutable runtime state",
            "runtime/logs/       = append-only operational telemetry",
            "launch external PowerShell or Python helpers must remain run-scoped "
            "and fail",
            "Potentially large `stdout`/`stderr` streams must be redirected to",
            "the full descendant process tree and fail the run if helper "
            "descendants remain",
            "Any mutable, generated, reproducible, or execution/run-produced output "
            "must be",
            "grouped under `runtime/` first and then routed",
            "into the appropriate governed",
            "Repository root describes the system;",
            "`runtime/` describes what the system",
            "produces while operating. If deleting a file would make the repository",
            "undefined or remove governed authority,",
            "that file is not runtime output and",
            "must remain under the governed source, policy, schema, registry, or docs",
            "surface that defines it.",
        ),
        REPOSITORY_VALIDATOR_GOVERNANCE_STANDARD: (
            "The validator must treat `runtime/` as the canonical grouping root for",
            "mutable, generated, reproducible, and execution/run-produced outputs",
            "before it",
            "validates subfolder placement.",
            "Files whose deletion would make the repository",
            "undefined do not belong under `runtime/`.",
            "Mutable, generated, reproducible, and execution/run-produced outputs are",
            "grouped under `runtime/`.",
            "Runtime state is stored under `runtime/state/`.",
            "Human-readable reports are stored under `runtime/reports/`.",
            "Machine-readable artifacts are stored under `runtime/artifacts/`.",
            "Docs are authority.",
            "Validator is enforcement.",
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "Runtime is not source-of-truth.",
            "LLM is not authority.",
            "Scores cannot hide blockers.",
            "LIVE remains blocked.",
        ),
        DOCS / "controls" / "control_repository_validation_rules.md": (
            "The validator treats `runtime/` as the canonical grouping root",
            "for mutable,",
            "`runtime/` grouping root enforcement",
            "external helper process isolation for quality-gate and `artifact_hygiene`",
            "large-output capture paths that must remain file-backed and run-scoped",
            "timeout-bound descendant process cleanup for PowerShell and Python helper",
            "runtime grouping root is preserved;",
            "generated, reproducible, and execution/run-produced outputs.",
            "resolve governed concept ownership by",
            "`authority_scope`",
            "KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT",
            "Operational specialization is allowed only when the lower",
            "narrower derived `authority_scope`",
            "If deleting a file",
            "would make the repository undefined, that file is not runtime output.",
        ),
        DOCS / "registries" / "registry_repository_folder_ownership_retention.md": (
            "`runtime/` is the canonical grouping root",
            "for mutable, generated, reproducible,",
            "and execution/run-produced outputs. If deleting a file",
            "would make the",
            "repository undefined or remove governed authority,",
            "it does not belong under",
            "`runtime/`.",
            (
                "| `runtime` | Runtime workspace | Local execution workspace | "
                "KEEP_DOMAIN_ROOT |"
            ),
            "manual | Canonical grouping root for mutable, generated, reproducible,",
            "and execution/run-produced outputs. Files whose deletion would make",
            "the repository",
            (
                "undefined must stay under the governed source, policy, schema, "
                "registry, or docs"
            ),
            "surface that owns them.",
        ),
        DOCUMENTATION_KNOWLEDGE_GOVERNANCE_STANDARD: (
            "AI4B-GOV-DKG-001",
            "Documentation and Knowledge Governance Standard",
            "GovernedKnowledgeObject",
            "RepositoryPolicy",
            "RepositoryArtifact schema",
            "deterministic repository_validator",
            "full quality gate",
            "duplicate active source-of-truth concept conflicts",
            "concept-level `authority_scope` ownership resolution",
            "lower-authority semantic override blockers",
            "non-code repository content language = en-US",
            "RUNNING_WITH_BLOCKERS",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
        ),
        AGENTS: (
            "The canonical constitution is "
            "`docs/governance/framework_core_vnext_governance.md`.",
            "`docs/governance/policy_organization_constitution_handbook.md`",
            "`docs/standards/standard_repository_file_governance.md`",
            "Codex workflows must load `docs/providers/instruction_codex_provider.md`.",
            "Claude workflows must load "
            "`docs/providers/instruction_claude_provider.md`.",
            "C3_GOVERNED",
            "DETERMINISTIC_FIRST",
            "LLM_ADVISORY_ONLY",
            "RISK_VETO IS HARD",
            "VALIDATION_VETO IS HARD",
            "ZERO_TOKEN",
            "LOGICAL_CAPABILITY != RUNTIME_AGENT",
            "producer needs independent verification",
            "`FAST`: Ruff + dmypy + affected tests",
            "only FULL may claim `FULL_VERIFIED`",
            "Credentials/tools do not grant authority",
            "GOVERNANCE_CONFLICT",
            "RUNNING_WITH_BLOCKERS",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
            "Do not modify protected governed Markdown without explicit user approval.",
            (
                "Repository root describes the system. `runtime/` describes what the "
                "system"
            ),
            "produces while operating. Mutable, generated, reproducible, and",
            "execution/run-produced outputs must be grouped under `runtime/`.",
            "If deleting a",
            (
                "file would make the repository undefined or remove governed "
                "authority, that"
            ),
            "file does not belong under `runtime/`.",
        ),
    }

    missing = {
        path.relative_to(ROOT).as_posix(): [
            fragment
            for fragment in fragments
            if fragment not in path.read_text(encoding="utf-8")
        ]
        for path, fragments in expected_by_document.items()
    }

    assert missing == {
        path.relative_to(ROOT).as_posix(): [] for path in expected_by_document
    }


def test_custom_instructions_use_vnext_action_and_scan_output_contract() -> None:
    text = CUSTOM_INSTRUCTIONS.read_text(encoding="utf-8")

    assert "* use BUY, SELL, HOLD, WAIT or NO_TRADE," in text
    assert "Leverage\nBudget/Margin\nR:R\nNews Risk\nDecision" in text
    assert "* only A*, A and B+ quality," in text
    assert "B_PLUS:" in text
    assert "`WAIT_FOR_RETEST` is a legacy/internal retest status" in text
    assert "* use BUY, SELL, HOLD, WAIT_FOR_RETEST or NO_TRADE," not in text
    assert "* only A* and A quality," not in text


def test_custom_instructions_preserve_validation_veto_and_decision_authority() -> None:
    text = CUSTOM_INSTRUCTIONS.read_text(encoding="utf-8")

    assert (
        "The Validation Agent is a hard deterministic veto, not the final decision\n"
        "authority. Decision Governance may produce the final `TradeDecision` only "
        "after\nRisk and Validation outcomes are applied."
    ) in text
    assert "Validation never grants execution or\nlive-order authority." in text
    assert "* return a validation approval," in text
    assert (
        "The Validation Agent is the final deterministic decision authority."
        not in text
    )


def test_instruction_context_router_avoids_default_corpus_loading() -> None:
    root_text = AGENTS.read_text(encoding="utf-8")
    normalized_root = re.sub(r"\s+", " ", root_text)

    assert (
        "Base context is this file plus the active adapter. Add nearest scoped "
        "`AGENTS.md` only for paths within its scope."
    ) in normalized_root
    assert "Route them; do not load by default." in root_text
    for route in (
        "| Ordinary source | Affected code/config/callers/contracts/tests |",
        "| Governance | Core; affected policy/schema/registry/compliance/tests |",
        "| Architecture | Core; architecture SoT; ADR/registry |",
        "| Risk/validation | Core; policy/schema/registry/code/tests |",
        (
            "| Decision/execution | Core; contracts/risk/validation/gates/"
            "rejection tests |"
        ),
        "| Quality | Profile runbook/config; runner/tests |",
        "| Governed docs | Repository/metadata standards; index/manifest |",
        "| Research | Lifecycle/OOS/walk-forward/provenance/tests |",
    ):
        assert route in root_text

    for adapter_path in (
        CODEX_PROVIDER_INSTRUCTIONS,
        CLAUDE_PROVIDER_INSTRUCTIONS,
    ):
        adapter_text = adapter_path.read_text(encoding="utf-8")
        normalized_adapter = re.sub(r"\s+", " ", adapter_text)
        assert (
            "Base context: `AGENTS.md` plus this adapter (two files)."
            in normalized_adapter
        )
        assert (
            "Add the nearest scoped `AGENTS.md` only for paths within its scope."
        ) in normalized_adapter
        assert "Route before other governed-source reads." in normalized_adapter
        assert "Do not preload the canonical map." in normalized_adapter
        assert "Escalate one source at a time" in normalized_adapter
        assert "then every applicable nested" not in normalized_adapter
        assert "Load additional governed sources named by the root contract" not in (
            normalized_adapter
        )
        assert "Load the governed sources named by the root contract" not in (
            normalized_adapter
        )


def test_live_order_lifecycle_contract_is_canonical_and_locked() -> None:
    contract_path = DOCS / "contracts" / "interface_contract_live_order_lifecycle.md"
    text = contract_path.read_text(encoding="utf-8")

    assert "document_id: AI4B-LIVE-ORDER-001" in text
    assert "## ELI10" in text
    assert "live-order-lifecycle.jsonl" in text
    assert "LIVE_ORDER_BLOCKED" in text

    manifest = json.loads(
        (
            ROOT / "config" / "governance" / "governed_document_lock_manifest.json"
        ).read_text(encoding="utf-8")
    )
    locked_paths = {entry["path"] for entry in manifest["locked_documents"]}
    assert "docs/contracts/interface_contract_live_order_lifecycle.md" in locked_paths

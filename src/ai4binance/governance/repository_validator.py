"""Deterministic repository policy and artifact validator."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import subprocess  # nosec B404
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

import yaml

from ai4binance.governance.authority import (
    detect_authority_conflicts,
    load_authority_graph,
    load_authority_layer_development_matrix,
    validate_authority_graph_layer_development,
    validate_authority_graph_metadata,
)
from ai4binance.governance.authority.model import AUTHORITY_LAYERS
from ai4binance.governance.blockers import BLOCKER_REGISTRY_PATH, load_blocker_registry
from ai4binance.governance.governance_enforcement_fabric import (
    FABRIC_PATH as GOVERNANCE_ENFORCEMENT_FABRIC_PATH,
)
from ai4binance.governance.governance_enforcement_fabric import (
    SCHEMA_PATH as GOVERNANCE_ENFORCEMENT_FABRIC_SCHEMA_PATH,
)
from ai4binance.governance.governance_enforcement_fabric import (
    evaluate_governance_enforcement_fabric,
    load_governance_enforcement_fabric,
)
from ai4binance.governance.technology_language_policy import (
    POLICY_PATH as TECHNOLOGY_LANGUAGE_POLICY_PATH,
)
from ai4binance.governance.technology_language_policy import (
    SCHEMA_PATH as TECHNOLOGY_LANGUAGE_SCHEMA_PATH,
)
from ai4binance.governance.technology_language_policy import (
    STANDARD_PATH as TECHNOLOGY_LANGUAGE_STANDARD_PATH,
)
from ai4binance.governance.technology_language_policy import (
    evaluate_technology_language_policy,
    load_technology_language_policy,
)
from ai4binance.governance_primitives import (
    AUTHORITY_BASIS_GOVERNED_METADATA_VALIDATED,
    AUTHORITY_BASIS_METADATA_MISSING,
    AUTHORITY_BASIS_PLACEMENT_HINT_ONLY,
    PLACEMENT_HINT_PREFIX,
)
from ai4binance.reporting import to_primitive


class RepositoryValidationStatus(StrEnum):
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


class RepositoryFindingSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RepositoryControlFamily(StrEnum):
    DOC_HYGIENE = "DOC_HYGIENE"
    ARTIFACT_HYGIENE = "ARTIFACT_HYGIENE"
    RUNTIME_HYGIENE = "RUNTIME_HYGIENE"
    CONFIG_HYGIENE = "CONFIG_HYGIENE"
    SCHEMA_HYGIENE = "SCHEMA_HYGIENE"
    POLICY_HYGIENE = "POLICY_HYGIENE"
    SOURCE_HYGIENE = "SOURCE_HYGIENE"
    REPOSITORY_CONFORMANCE = "REPOSITORY_CONFORMANCE"


class RepositoryFindingKind(StrEnum):
    UNKNOWN_TOP_LEVEL_PATH = "UNKNOWN_TOP_LEVEL_PATH"
    LEGACY_RUNTIME_ROOT_LEAKAGE = "LEGACY_RUNTIME_ROOT_LEAKAGE"
    PYTHON_PACKAGE_NAMING_VIOLATION = "PYTHON_PACKAGE_NAMING_VIOLATION"
    PYTHON_FILE_NAMING_VIOLATION = "PYTHON_FILE_NAMING_VIOLATION"
    FORBIDDEN_SOURCE_FILENAME = "FORBIDDEN_SOURCE_FILENAME"
    SOURCE_VERSION_FILENAME = "SOURCE_VERSION_FILENAME"
    GENERATED_ARTIFACT_INSIDE_SRC = "GENERATED_ARTIFACT_INSIDE_SRC"
    RUNTIME_STATE_INSIDE_SRC = "RUNTIME_STATE_INSIDE_SRC"
    HARDCODED_ABSOLUTE_PATH = "HARDCODED_ABSOLUTE_PATH"
    CANONICAL_IMPORT_BOUNDARY_VIOLATION = "CANONICAL_IMPORT_BOUNDARY_VIOLATION"
    CANONICAL_LAYER_OWNERSHIP_AMBIGUITY = "CANONICAL_LAYER_OWNERSHIP_AMBIGUITY"
    KNOWLEDGE_METADATA_MISSING = "KNOWLEDGE_METADATA_MISSING"
    KNOWLEDGE_METADATA_INVALID = "KNOWLEDGE_METADATA_INVALID"
    KNOWLEDGE_LIFECYCLE_VIOLATION = "KNOWLEDGE_LIFECYCLE_VIOLATION"
    KNOWLEDGE_ID_DUPLICATE = "KNOWLEDGE_ID_DUPLICATE"
    KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT = "KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT"
    KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT = "KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT"
    SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION = "SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION"
    KNOWLEDGE_REQUIRED_SECTION_MISSING = "KNOWLEDGE_REQUIRED_SECTION_MISSING"
    KNOWLEDGE_LANGUAGE_VIOLATION = "KNOWLEDGE_LANGUAGE_VIOLATION"
    NON_CODE_CONTENT_LANGUAGE_VIOLATION = "NON_CODE_CONTENT_LANGUAGE_VIOLATION"
    RUNTIME_MARKDOWN_AUTHORITY_VIOLATION = "RUNTIME_MARKDOWN_AUTHORITY_VIOLATION"
    GOVERNED_DOCUMENT_LOCK_VIOLATION = "GOVERNED_DOCUMENT_LOCK_VIOLATION"
    KNOWLEDGE_OUTPUT_WRITE_FAILED = "KNOWLEDGE_OUTPUT_WRITE_FAILED"
    CANONICAL_TOP_LEVEL_MISSING = "CANONICAL_TOP_LEVEL_MISSING"
    BLOCKER_REGISTRY_INVALID = "BLOCKER_REGISTRY_INVALID"
    AUTHORITY_GRAPH_INVALID = "AUTHORITY_GRAPH_INVALID"
    AUTHORITY_GRAPH_CONFLICT = "AUTHORITY_GRAPH_CONFLICT"
    MIRROR_FORBIDDEN_PATH = "MIRROR_FORBIDDEN_PATH"
    MIRROR_PRIVATE_EVIDENCE_VIOLATION = "MIRROR_PRIVATE_EVIDENCE_VIOLATION"
    MIRROR_RUNTIME_POLLUTION = "MIRROR_RUNTIME_POLLUTION"
    MIRROR_CACHE_POLLUTION = "MIRROR_CACHE_POLLUTION"
    MIRROR_GENERATED_ARTIFACT = "MIRROR_GENERATED_ARTIFACT"
    MIRROR_UNKNOWN_PATH = "MIRROR_UNKNOWN_PATH"
    MIRROR_SOURCE_OF_TRUTH_VIOLATION = "MIRROR_SOURCE_OF_TRUTH_VIOLATION"
    TECHNOLOGY_LANGUAGE_POLICY_VIOLATION = "TECHNOLOGY_LANGUAGE_POLICY_VIOLATION"
    TERMINOLOGY_POLICY_VIOLATION = "TERMINOLOGY_POLICY_VIOLATION"
    TERMINOLOGY_PROHIBITED_TERM = "TERMINOLOGY_PROHIBITED_TERM"
    TERMINOLOGY_DEPRECATED_ALIAS = "TERMINOLOGY_DEPRECATED_ALIAS"
    GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION = "GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION"


class RepositoryArtifactType(StrEnum):
    SOURCE_CODE = "SOURCE_CODE"
    CONFIG = "CONFIG"
    SCHEMA = "SCHEMA"
    POLICY = "POLICY"
    GOVERNANCE = "GOVERNANCE"
    ONTOLOGY = "ONTOLOGY"
    DATA = "DATA"
    MODEL = "MODEL"
    REPORT = "REPORT"
    LOG = "LOG"
    STATE = "STATE"
    RUNTIME = "RUNTIME"
    CACHE = "CACHE"
    TEST = "TEST"
    WORKFLOW = "WORKFLOW"
    MIGRATION = "MIGRATION"
    EVIDENCE = "EVIDENCE"
    ARCHIVE = "ARCHIVE"
    ARTIFACT = "ARTIFACT"


class RepositoryArtifactClass(StrEnum):
    SOURCE = "SOURCE"
    GOVERNANCE = "GOVERNANCE"
    RUNTIME = "RUNTIME"
    CACHE = "CACHE"
    REPORT = "REPORT"
    ARCHIVE = "ARCHIVE"


class RepositoryArtifactLifecycle(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_CANDIDATE = "LIVE_CANDIDATE"
    LIVE_APPROVED = "LIVE_APPROVED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    ARCHIVED = "ARCHIVED"


class KnowledgeObjectType(StrEnum):
    REGULATION = "REGULATION"
    STANDARD = "STANDARD"
    POLICY = "POLICY"
    FRAMEWORK = "FRAMEWORK"
    INSTRUCTION = "INSTRUCTION"
    SCHEMA = "SCHEMA"
    ENTITY_RULE = "ENTITY_RULE"
    RELATIONSHIP_RULE = "RELATIONSHIP_RULE"
    OUTPUT_CONTRACT = "OUTPUT_CONTRACT"
    DATA_CONTRACT = "DATA_CONTRACT"
    EVENT_CONTRACT = "EVENT_CONTRACT"
    INTERFACE_CONTRACT = "INTERFACE_CONTRACT"
    DECISION_RULE = "DECISION_RULE"
    STATE_MODEL = "STATE_MODEL"
    WORKFLOW = "WORKFLOW"
    CONSTRAINT = "CONSTRAINT"
    INVARIANT = "INVARIANT"
    DEFINITION = "DEFINITION"
    GLOSSARY = "GLOSSARY"
    ROLE = "ROLE"
    PERMISSION_PROFILE = "PERMISSION_PROFILE"
    AUTHORITY_MATRIX = "AUTHORITY_MATRIX"
    VALIDATION_SPEC = "VALIDATION_SPEC"
    TEST_CONTRACT = "TEST_CONTRACT"
    EVIDENCE_REQUIREMENT = "EVIDENCE_REQUIREMENT"
    PROVENANCE = "PROVENANCE"
    LINEAGE = "LINEAGE"
    PROCEDURE = "PROCEDURE"
    RUNBOOK = "RUNBOOK"
    FAILURE_POLICY = "FAILURE_POLICY"
    RECOVERY_RULE = "RECOVERY_RULE"
    ESCALATION_RULE = "ESCALATION_RULE"
    ALERT_RULE = "ALERT_RULE"
    RETENTION_RULE = "RETENTION_RULE"
    STRATEGY_DEFINITION = "STRATEGY_DEFINITION"
    SETUP_DEFINITION = "SETUP_DEFINITION"
    FEATURE_DEFINITION = "FEATURE_DEFINITION"
    INDICATOR_DEFINITION = "INDICATOR_DEFINITION"
    REGIME_DEFINITION = "REGIME_DEFINITION"
    RISK_MODEL = "RISK_MODEL"
    EXECUTION_PROFILE = "EXECUTION_PROFILE"
    PARAMETER_SET = "PARAMETER_SET"
    AGENT_CONTRACT = "AGENT_CONTRACT"
    PROMPT_CONTRACT = "PROMPT_CONTRACT"
    TOOL_CONTRACT = "TOOL_CONTRACT"
    MODEL_CARD = "MODEL_CARD"
    AGENT_CARD = "AGENT_CARD"
    STRATEGY_CARD = "STRATEGY_CARD"
    EXPERIMENT = "EXPERIMENT"
    LESSON = "LESSON"
    FAILURE_PATTERN = "FAILURE_PATTERN"
    DRIFT_OBSERVATION = "DRIFT_OBSERVATION"
    IMPROVEMENT_CANDIDATE = "IMPROVEMENT_CANDIDATE"
    EXCEPTION = "EXCEPTION"
    WAIVER = "WAIVER"
    ADR = "ADR"
    REGISTRY = "REGISTRY"
    CONTROL = "CONTROL"
    PROVIDER_ADAPTER = "PROVIDER_ADAPTER"
    REFERENCE = "REFERENCE"
    TEMPLATE_SET = "TEMPLATE_SET"


class KnowledgeAuthorityLevel(StrEnum):
    REPOSITORY = "REPOSITORY"
    EXTERNAL_AUTHORITY = "EXTERNAL_AUTHORITY"
    ENFORCEABLE = "ENFORCEABLE"
    NORMATIVE = "NORMATIVE"
    ADVISORY = "ADVISORY"
    INFORMATIONAL = "INFORMATIONAL"
    PROVIDER_ADAPTER = "PROVIDER_ADAPTER"
    REFERENCE = "REFERENCE"


class KnowledgeAuthorityEffect(StrEnum):
    MANDATORY_CONSTRAINT = "MANDATORY_CONSTRAINT"
    NORMATIVE_CONSTRAINT = "NORMATIVE_CONSTRAINT"
    OPERATIONAL_SPECIALIZATION = "OPERATIONAL_SPECIALIZATION"
    IMPLEMENTATION = "IMPLEMENTATION"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"


class KnowledgeContentRole(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    POLICY_AS_CODE = "POLICY_AS_CODE"
    EXPLANATORY = "EXPLANATORY"
    GENERATED = "GENERATED"
    DERIVED = "DERIVED"
    HISTORICAL = "HISTORICAL"
    OPERATIONAL = "OPERATIONAL"
    EVIDENCE = "EVIDENCE"


class KnowledgeLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    SUSPENDED = "SUSPENDED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class KnowledgeClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    SECRET = "SEC" + "RET"


_LOWER_SNAKE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PYTHON_FILE_RE = re.compile(r"^(__init__|[a-z_][a-z0-9_]*)\.py$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_KNOWLEDGE_ID_RE = re.compile(r"^AI4B(?:-[A-Z0-9]+){2,}-\d{3}$")
_SOURCE_VERSION_RE = re.compile(
    r"(^|_)(v\d+|final|final\d+|final_final|new_final\d*|fixed)(_|\.py$)"
)
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?:[A-Za-z]:[/\\][^\s\"'`),;]+|/(?:Users|home|tmp)/[^\s\"'`),;]+)"
)
_NON_ENGLISH_ALLOWED_LITERALS = (".çzüö",)
GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH = (
    "config/governance/governed_document_lock_manifest.json"
)
REPOSITORY_MIRROR_POLICY_PATH = "config/governance/repository_mirror_policy.yaml"
REPOSITORY_VALIDATOR_POLICY_PATH = "policies/repository-validator/manifest-policy.json"
AUTHORITY_GRAPH_REGISTRY_PATH = "docs/registries/registry_authority_graph.yaml"
GOVERNED_DOCUMENT_ALLOWED_CHANGE_PROCESS = "WRITTEN_OWNER_APPROVAL_REQUIRED"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_LEGACY_RUNTIME_ROOT_TARGETS = {
    "artifacts": "runtime/artifacts",
    "data": "runtime/data",
    "logs": "runtime/logs",
    "state": "runtime/state",
}
_REPOSITORY_AUTHORITY_LAYERS = AUTHORITY_LAYERS
_OPERATIONAL_AUTHORITY_METADATA_PREFIXES: tuple[str, ...] = (
    "docs/workflows/",
    "docs/procedures/",
    "docs/runbooks/",
)
_AUTHORITY_SCOPE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_LEGACY_AUTHORITY_EFFECT_ALIASES: dict[str, KnowledgeAuthorityEffect] = {
    "REPOSITORY_CONTROL": KnowledgeAuthorityEffect.NORMATIVE_CONSTRAINT,
    "EXTERNAL_MANDATE": KnowledgeAuthorityEffect.MANDATORY_CONSTRAINT,
    "MACHINE_ENFORCEMENT": KnowledgeAuthorityEffect.IMPLEMENTATION,
    "NORMATIVE_REQUIREMENT": KnowledgeAuthorityEffect.NORMATIVE_CONSTRAINT,
    "ADVISORY_GUIDANCE": KnowledgeAuthorityEffect.EVIDENCE_ONLY,
    "INFORMATIONAL_CONTEXT": KnowledgeAuthorityEffect.EVIDENCE_ONLY,
    "REFERENCE_CONTEXT": KnowledgeAuthorityEffect.REFERENCE_ONLY,
}
_FAMILY_INDEX_KNOWLEDGE_PATHS = frozenset(
    {
        "docs/governance/policy_organization_constitution_handbook.md",
        "docs/registries/registry_documentation_index.md",
    }
)
_PROVIDER_ADAPTER_KNOWLEDGE_PATHS = frozenset(
    {
        "CLAUDE.md",
        "GEMINI.md",
        "docs/governance/instruction_core_custom_instructions.md",
        "docs/providers/instruction_codex_provider.md",
        "docs/providers/instruction_claude_provider.md",
        "docs/providers/runbook_tradingview_mcp_codex_connection.md",
    }
)
DKG_REQUIRED_SECTION_TITLES: tuple[str, ...] = (
    "Purpose",
    "Governing Concept",
    "Core Principles",
    "Governed System Knowledge Taxonomy",
    "Normative Knowledge",
    "Semantic Knowledge",
    "Structural Knowledge",
    "Behavioral Knowledge",
    "Authority Knowledge",
    "Operational Knowledge",
    "Validation Knowledge",
    "Evidence Knowledge",
    "Learning Knowledge",
    "Governance Metadata",
    "Mandatory GovernedKnowledgeObject Schema",
    "Knowledge ID Standard",
    "Knowledge Type Registry",
    "Normative Language",
    "Authority Levels",
    "Authority Precedence",
    "Conflict Resolution",
    "Content Role",
    "Source-of-Truth Governance",
    "Authoritative vs Explanatory Separation",
    "Document Lifecycle",
    "Lifecycle Transition Rules",
    "Production Authority Rule",
    "Versioning Standard",
    "MAJOR Version",
    "MINOR Version",
    "PATCH Version",
    "Version Immutability",
    "Supersession",
    "Schema Knowledge Format",
    "Instruction Knowledge Format",
    "Entity Rule Format",
    "Relationship Rule Format",
    "Policy Format",
    "Control Format",
    "Standard Format",
    "Framework Format",
    "Regulation Format",
    "Registry Format",
    "Output Contract Format",
    "Data Contract Format",
    "Event Contract Format",
    "Interface Contract Format",
    "Decision Rule Format",
    "Invariant Format",
    "Constraint Format",
    "State Model Format",
    "Workflow Format",
    "Validation Specification Format",
    "Test Contract Format",
    "Evidence Requirement Format",
    "Provenance Format",
    "Lineage Format",
    "Decision Record",
    "Strategy Definition Format",
    "Setup Definition Format",
    "Feature Definition",
    "Indicator Definition",
    "Regime Definition",
    "Risk Model Format",
    "Execution Profile",
    "Parameter Set",
    "Agent Contract",
    "Prompt Contract",
    "Tool Contract",
    "Permission Profile",
    "Authority Matrix",
    "Exception and Waiver",
    "ADR: Architecture Decision Record",
    "Failure Policy",
    "Recovery Rule",
    "Escalation Rule",
    "Alert Rule",
    "Retention Rule",
    "Procedure Format",
    "Runbook Format",
    "Learning Object Lifecycle",
    "Experiment Format",
    "Failure Pattern",
    "Drift Observation",
    "Improvement Candidate",
    "Registry Architecture",
    "Registry Source of Truth",
    "Cross-reference Standard",
    "Dependency Governance",
    "Change Impact Analysis",
    "Knowledge Classification",
    "Document Directory Standard",
    "Machine-readable Knowledge Locations",
    "Documentation Metadata Header",
    "Review Governance",
    "Mandatory Review Triggers",
    "Documentation Validator",
    "Validator Results",
    "Hard Blockers",
    "Knowledge Governance Audit Trail",
    "Knowledge Lineage",
    "Regulation Mapping Model",
    "Architecture Knowledge Model",
    "Agent Knowledge Model",
    "Decision Knowledge Model",
    "Learning Knowledge Model",
    "Human vs Machine Authority",
    "LLM Knowledge Boundary",
    "Governance Change Workflow",
    "Prohibited Practices",
    "Minimum Acceptance Criteria",
    "Recommended Knowledge Governance Architecture",
    "System-of-Systems Knowledge Model",
    "Final Governing Principle",
    "Target State",
)
DKG_CORE_REQUIRED_SECTION_TITLES: tuple[str, ...] = (
    "Repository Content Language",
    "Purpose",
    "Core Principles",
    "Mandatory GovernedKnowledgeObject Schema",
    "Knowledge ID Standard",
    "Authority Levels",
    "Authority Precedence",
    "Conflict Resolution",
    "Source-of-Truth Governance",
    "LLM Knowledge Boundary",
    "Minimum Acceptance Criteria",
    "Constitutional Lock",
    "Target State",
)
_CANONICAL_LAYER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("core", "ai4binance.core"),
    ("domain", "ai4binance.domain"),
    ("application", "ai4binance.application"),
    ("compatibility", "ai4binance.compatibility"),
    ("infrastructure", "ai4binance.infrastructure"),
    ("integrations", "ai4binance.integrations"),
    ("cli", "ai4binance.cli"),
)
_CANONICAL_LAYER_ALLOWED_DEPENDENCIES: dict[str, frozenset[str]] = {
    "core": frozenset({"core"}),
    "domain": frozenset({"core", "domain"}),
    "application": frozenset({"core", "domain", "application"}),
    "compatibility": frozenset({"core", "domain"}),
    "infrastructure": frozenset({"core", "domain", "application", "infrastructure"}),
    "integrations": frozenset({"core", "domain", "application", "integrations"}),
}
CANONICAL_ROOT_FILES: tuple[str, ...] = (
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "pyproject.toml",
    "uv.lock",
)
CANONICAL_TOP_LEVEL_PATHS: tuple[str, ...] = (
    "config",
    "docs",
    "migrations",
    "runtime",
    "schemas",
    "scripts",
    "src",
    "tests",
    "tools",
)
SUPPORT_TOP_LEVEL_PATHS: tuple[str, ...] = (
    ".agents",
    ".codex",
    ".gitleaksignore",
    ".github",
    ".pytest-tmp-open-web",
    ".venv",
    ".vscode",
    "examples",
    "factory",
    "LICENSE",
    "publication",
    "requirements.txt",
    "research",
)
LEGACY_TOP_LEVEL_PATHS: tuple[str, ...] = (
    "alerts",
    "analysis",
    "backtest",
    "futures",
    "intelligence",
    "news",
    "ontology",
    "opportunities",
    "orders",
    "policies",
    "secrets",
    "spot",
    "wallet",
    "workflows",
)

GOVERNED_OPERATIONAL_EXCEPTION_MARKDOWN_PATHS: tuple[str, ...] = (
    "factory/brief.md",
    "factory/guide.md",
    "factory/handoff.md",
    "factory/plan.md",
    "factory/review.md",
)

NONCANONICAL_OPERATIONAL_MARKDOWN_PATHS: tuple[str, ...] = (
    "factory/log.md",
    "factory/progress.md",
    "factory/state.md",
)


@dataclass(frozen=True, slots=True)
class RepositoryPolicy:
    """Machine-verifiable repository governance policy."""

    policy_id: str
    version: str
    allowed_top_level_paths: tuple[str, ...]
    source_roots: tuple[str, ...]
    test_roots: tuple[str, ...]
    docs_roots: tuple[str, ...]
    generated_roots: tuple[str, ...]
    protected_roots: tuple[str, ...]
    ignored_parts: tuple[str, ...]
    cache_parts: tuple[str, ...]
    legacy_path_targets: dict[str, str]
    forbidden_python_filenames: tuple[str, ...]
    allowed_absolute_path_literals: tuple[str, ...]
    knowledge_metadata_required_paths: tuple[str, ...]
    english_only_knowledge_paths: tuple[str, ...]
    non_code_content_language: str
    knowledge_section_requirements: dict[str, tuple[str, ...]]
    owner_by_top_level: dict[str, str]
    compatibility_imports: dict[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        _require_non_empty("policy_id", self.policy_id)
        _require_non_empty("version", self.version)
        _require_unique_nonblank(
            "allowed_top_level_paths", self.allowed_top_level_paths
        )
        _require_unique_nonblank("source_roots", self.source_roots)
        _require_unique_nonblank("test_roots", self.test_roots)
        _require_unique_nonblank("docs_roots", self.docs_roots)
        _require_unique_nonblank("generated_roots", self.generated_roots)
        _require_unique_nonblank("protected_roots", self.protected_roots)
        _require_unique_nonblank("ignored_parts", self.ignored_parts)
        _require_unique_nonblank("cache_parts", self.cache_parts)
        _require_unique_nonblank(
            "forbidden_python_filenames", self.forbidden_python_filenames
        )
        _require_unique_nonblank(
            "knowledge_metadata_required_paths",
            self.knowledge_metadata_required_paths,
        )
        _require_unique_nonblank(
            "english_only_knowledge_paths",
            self.english_only_knowledge_paths,
        )
        _require_non_empty("non_code_content_language", self.non_code_content_language)
        if self.non_code_content_language != "en-US":
            raise ValueError("non-code repository content language must be en-US")
        for relative, sections in self.knowledge_section_requirements.items():
            _require_non_empty("knowledge section path", relative)
            _require_unique_nonblank(
                f"knowledge_section_requirements[{relative}]", sections
            )
        _validate_compatibility_imports(self.compatibility_imports)

    @classmethod
    def ai4binance_vnext(cls) -> RepositoryPolicy:
        """Return the current AI4BINANCE repository policy baseline."""
        allowed = (
            *CANONICAL_ROOT_FILES,
            *CANONICAL_TOP_LEVEL_PATHS,
            *SUPPORT_TOP_LEVEL_PATHS,
            *LEGACY_TOP_LEVEL_PATHS,
        )
        owners = {
            ".gitleaksignore": "Security",
            "LICENSE": "Governance",
            "examples": "Documentation",
            "publication": "Governance",
            "src": "Engineering",
            "tests": "Quality",
            "docs": "Governance",
            "scripts": "Operations",
            "config": "Governance",
            "schemas": "Governance",
            "policies": "Governance",
            "ontology": "Governance",
            "workflows": "Governance",
            "research": "Research",
            "artifacts": "Audit",
            "reports": "Reporting",
            "runtime": "Runtime",
            "logs": "Observability",
            "secrets": "Security",
            "data": "Data",
            "backtest": "Validation",
            "models": "ModelGovernance",
            "wallet": "Portfolio",
            "orders": "ExecutionAudit",
            "opportunities": "AdvisoryRadar",
            "migrations": "Engineering",
            "tools": "Engineering",
        }
        return cls(
            policy_id="AI4B-GOV-REPO-POLICY",
            version="1.3.1",
            allowed_top_level_paths=allowed,
            source_roots=("src/ai4binance",),
            test_roots=("tests",),
            docs_roots=(
                "docs",
                "README.md",
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
            ),
            generated_roots=("runtime/artifacts", "runtime/logs"),
            protected_roots=(
                "secrets",
                "runtime/state/private",
                "runtime/state/private/**",
                "runtime/models",
                "runtime/models/**",
                ".venv",
            ),
            ignored_parts=(
                ".git",
                ".venv",
                ".coverage",
                "__pycache__",
                ".mypy_cache",
                ".ruff_cache",
                ".pytest_cache",
                ".pytest-tmp",
                ".tmp",
                ".tmp-alias-check",
                "ai4binance.egg-info",
                "archive",
                "secrets",
                "backtest",
                "wallet",
                "orders",
                "opportunities",
                "runtime",
                "tools",
            ),
            cache_parts=(
                ".coverage",
                ".hypothesis",
                ".mypy_cache",
                ".pytest_cache",
                ".pytest-tmp",
                ".pytest-tmp-open-web",
                ".ruff_cache",
                "__pycache__",
                "ai4binance.egg-info",
            ),
            legacy_path_targets={
                "clean_codes.md": (
                    "docs/standards/"
                    "standard_engineering_python_clean_code_vscode_development.md"
                ),
                "custom_instructions_core.md": (
                    "docs/governance/instruction_core_custom_instructions.md"
                ),
            },
            forbidden_python_filenames=(
                "backup.py",
                "common.py",
                "copy.py",
                "data.py",
                "final.py",
                "final2.py",
                "final_final.py",
                "functions.py",
                "helper.py",
                "helpers.py",
                "misc.py",
                "new.py",
                "new2.py",
                "old.py",
                "temp.py",
                "test.py",
                "test2.py",
                "tmp.py",
                "utils.py",
            ),
            allowed_absolute_path_literals=(),
            knowledge_metadata_required_paths=(
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
                "docs/providers/instruction_codex_provider.md",
                "docs/governance/instruction_core_custom_instructions.md",
                "docs/governance/policy_organization_constitution_handbook.md",
                "docs/governance/framework_core_vnext_governance.md",
                "docs/compliance/registry_compliance_matrix.md",
                "docs/standards/standard_repository_file_governance.md",
                (
                    "docs/standards/"
                    "standard_engineering_python_clean_code_vscode_development.md"
                ),
                "docs/standards/standard_documentation_knowledge_governance.md",
                "docs/standards/standard_terminology_governance.md",
            ),
            english_only_knowledge_paths=(
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
                "docs/providers/instruction_codex_provider.md",
                "docs/governance/instruction_core_custom_instructions.md",
                "docs/governance/policy_organization_constitution_handbook.md",
                "docs/governance/framework_core_vnext_governance.md",
                "docs/compliance/registry_compliance_matrix.md",
                "docs/standards/standard_repository_file_governance.md",
                (
                    "docs/standards/"
                    "standard_engineering_python_clean_code_vscode_development.md"
                ),
                "docs/standards/standard_documentation_knowledge_governance.md",
                "docs/standards/standard_terminology_governance.md",
            ),
            non_code_content_language="en-US",
            knowledge_section_requirements={
                "docs/standards/standard_documentation_knowledge_governance.md": (
                    DKG_CORE_REQUIRED_SECTION_TITLES
                ),
            },
            owner_by_top_level=owners,
            compatibility_imports={
                "ai4binance.application.opportunity_monitor": (
                    "ai4binance.compatibility.opportunity_monitor",
                ),
                "ai4binance.compatibility.opportunity_monitor": (
                    "ai4binance.agents.catalog",
                    "ai4binance.agents.data_quality_gate",
                    "ai4binance.data.archive",
                    "ai4binance.data.market_history_sync",
                    "ai4binance.opportunity_intelligence",
                    "ai4binance.opportunity_ledger",
                    "ai4binance.opportunity_outcomes",
                    "ai4binance.opportunity_radar",
                    "ai4binance.reporting",
                    "ai4binance.schemas",
                    "ai4binance.storage",
                    "ai4binance.storage.jsonl",
                ),
            },
        )


class MirrorPathClassification(StrEnum):
    SCM_INTERNAL = "SCM_INTERNAL"
    CACHE = "CACHE"
    TEST_CACHE = "TEST_CACHE"
    TEST_TEMP = "TEST_TEMP"
    GENERATED = "GENERATED"
    PRIVATE = "PRIVATE"
    SECRET = "SEC" + "RET"
    RUNTIME_STATE = "RUNTIME_STATE"
    RUNTIME_DATA = "RUNTIME_DATA"
    RUNTIME_LOG = "RUNTIME_LOG"
    TEMP = "TEMP"
    SOURCE = "SOURCE"
    TEST = "TEST"
    GOVERNED_KNOWLEDGE = "GOVERNED_KNOWLEDGE"
    CONFIG = "CONFIG"
    CONTRACT = "CONTRACT"
    OPERATIONAL_SURFACE = "OPERATIONAL_SURFACE"
    MIGRATION = "MIGRATION"
    TOOLING = "TOOLING"
    AUDIT_EVIDENCE = "AUDIT_EVIDENCE"
    REPORT = "REPORT"
    SELECTIVE_ARCHIVE = "SELECTIVE_ARCHIVE"
    UNKNOWN = "UNKNOWN"


class MirrorCleanupAction(StrEnum):
    KEEP_IN_MIRROR = "KEEP_IN_MIRROR"
    REMOVE_FROM_MIRROR = "REMOVE_FROM_MIRROR"
    QUARANTINE_FOR_REVIEW = "QUARANTINE_FOR_REVIEW"


@dataclass(frozen=True, slots=True)
class RepositoryMirrorPolicy:
    """Machine-readable policy for non-authoritative repository mirrors."""

    policy_id: str
    version: str
    status: str
    mirror_role: str
    mirror_authority: str
    may_be_source_of_truth: bool
    may_override_canonical: bool
    default_action: str
    allowed_exact_paths: tuple[str, ...]
    allowed_prefixes: tuple[str, ...]
    selective_prefixes: tuple[str, ...]
    hard_exclude_patterns: tuple[str, ...]
    private_patterns: tuple[str, ...]
    local_only_prefixes: tuple[str, ...]
    never_mirror_prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty("mirror policy_id", self.policy_id)
        _require_non_empty("mirror policy version", self.version)
        _require_non_empty("mirror status", self.status)
        _require_non_empty("mirror role", self.mirror_role)
        _require_non_empty("mirror authority", self.mirror_authority)
        _require_non_empty("mirror default_action", self.default_action)
        if self.mirror_role != "NON_CANONICAL_MIRROR":
            raise ValueError("mirror role must be NON_CANONICAL_MIRROR")
        if self.mirror_authority != "NONE":
            raise ValueError("mirror authority must be NONE")
        if self.may_be_source_of_truth or self.may_override_canonical:
            raise ValueError("mirror policy cannot grant repository authority")
        if self.default_action != "EXCLUDE":
            raise ValueError("mirror policy must be allowlist-first")
        _require_unique_nonblank("allowed_exact_paths", self.allowed_exact_paths)
        _require_unique_nonblank("allowed_prefixes", self.allowed_prefixes)
        _require_unique_nonblank("selective_prefixes", self.selective_prefixes)
        _require_unique_nonblank("hard_exclude_patterns", self.hard_exclude_patterns)
        _require_unique_nonblank("private_patterns", self.private_patterns)
        _require_unique_nonblank("local_only_prefixes", self.local_only_prefixes)
        _require_unique_nonblank("never_mirror_prefixes", self.never_mirror_prefixes)

    @classmethod
    def ai4binance_vnext(cls) -> RepositoryMirrorPolicy:
        """Return the current AI4BINANCE mirror hygiene policy baseline."""
        return cls(
            policy_id="AI4B-GOV-MIRROR-HYGIENE-001",
            version="1.0.0",
            status="ACTIVE",
            mirror_role="NON_CANONICAL_MIRROR",
            mirror_authority="NONE",
            may_be_source_of_truth=False,
            may_override_canonical=False,
            default_action="EXCLUDE",
            allowed_exact_paths=(
                ".env.example",
                ".gitattributes",
                ".gitignore",
                ".python-version",
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
                "README.md",
                "pyproject.toml",
                "uv.lock",
            ),
            allowed_prefixes=(
                ".agents",
                ".codex",
                ".github",
                "config",
                "docs",
                "migrations",
                "schemas",
                "scripts",
                "src",
                "tests",
                "tools",
            ),
            selective_prefixes=(
                "runtime/artifacts/repository_validation/governance",
                "runtime/artifacts/quality/gate",
                "runtime/artifacts/repository_validation",
                "runtime/artifacts/assurance/security",
                "runtime/audit",
                "runtime/evidence",
                "runtime/reports",
            ),
            hard_exclude_patterns=(
                ".git",
                ".git/**",
                ".mypy_cache",
                ".mypy_cache/**",
                ".ruff_cache",
                ".ruff_cache/**",
                ".pytest_cache",
                ".pytest_cache/**",
                ".pytest-tmp",
                ".pytest-tmp/**",
                ".hypothesis",
                ".hypothesis/**",
                ".coverage",
                ".coverage.*",
                "coverage.xml",
                "htmlcov",
                "htmlcov/**",
                "**/__pycache__",
                "**/__pycache__/**",
                "**/*.pyc",
                "**/*.pyo",
                "**/*.tmp",
                "**/*.bak",
                "**/*.swp",
                "**/*.egg-info",
                "**/*.egg-info/**",
                "src/*.egg-info",
                "src/*.egg-info/**",
            ),
            private_patterns=(
                ".env",
                ".env.*",
                "secrets",
                "secrets/**",
                "runtime/state/private",
                "runtime/state/private/**",
                "runtime/private",
                "runtime/private/**",
                "artifacts/**/private",
                "artifacts/**/private/**",
                "runtime/artifacts/**/private",
                "runtime/artifacts/**/private/**",
                "**/*credential*",
                "**/*secret*",
            ),
            local_only_prefixes=(
                "logs",
                "runtime/data",
                "runtime/logs",
                "runtime/state",
            ),
            never_mirror_prefixes=(
                "artifacts/cache",
                "artifacts/test_temp",
                "artifacts/tmp",
                "runtime/tmp/test_temp",
                "runtime/private",
                "runtime/tmp",
            ),
        )


@dataclass(frozen=True, slots=True)
class MirrorInventoryEntry:
    """One normalized mirror inventory entry."""

    path: str
    source_of_truth: bool = False
    authority: str | None = None
    git_tracked: bool | None = None

    def __post_init__(self) -> None:
        _require_non_empty("mirror inventory path", self.path)
        if "\\" in self.path or self.path.startswith("/"):
            raise ValueError("mirror inventory path must be repository-relative posix")


@dataclass(frozen=True, slots=True)
class MirrorCleanupPlanEntry:
    """Report-only cleanup recommendation for mirror pollution."""

    path: str
    classification: MirrorPathClassification
    canonical_required: bool
    mirror_action: MirrorCleanupAction
    local_action: str
    risk: str
    approval_required: bool


@dataclass(frozen=True, slots=True)
class MirrorHygieneReport:
    """Deterministic mirror hygiene report; it never mutates mirror contents."""

    policy_id: str
    policy_version: str
    mirror_manifest_path: str
    analyzed_at_utc: str
    status: RepositoryValidationStatus
    mirror_role: str
    mirror_authority: str
    mirror_source_of_truth: bool
    entry_count: int
    findings: tuple[RepositoryValidationFinding, ...]
    cleanup_plan: tuple[MirrorCleanupPlanEntry, ...]
    blockers: tuple[str, ...]
    dashboard_metrics: dict[str, int | float]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("mirror policy_id", self.policy_id)
        _require_non_empty("mirror_manifest_path", self.mirror_manifest_path)
        _require_non_empty("mirror_role", self.mirror_role)
        _require_non_empty("mirror_authority", self.mirror_authority)
        if self.mirror_source_of_truth:
            raise ValueError("mirror reports cannot grant source-of-truth authority")
        if self.status is RepositoryValidationStatus.PASS and self.blockers:
            raise ValueError("passing mirror validation cannot contain blockers")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("mirror validation cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("mirror validation cannot authorize live trading")

    def to_payload(self) -> dict[str, object]:
        payload = to_primitive(self)
        if not isinstance(payload, dict):
            raise RuntimeError("MIRROR_HYGIENE_PAYLOAD_INVALID")
        return payload


@dataclass(frozen=True, slots=True)
class RepositoryArtifact:
    """RepositoryArtifact ontology entity for source and governance files."""

    artifact_id: str
    artifact_type: RepositoryArtifactType
    artifact_class: RepositoryArtifactClass
    domain: str
    owner: str
    canonical_path: str
    filename: str
    schema_version: str | None
    lifecycle_status: RepositoryArtifactLifecycle
    generated: bool
    immutable: bool
    sensitive: bool
    git_tracked: bool
    checksum: str | None
    file_id: str = ""
    path: str = ""
    mime_type: str = "application/octet-stream"
    size: int = 0
    modified_time: str = ""
    shared_status: str = "LOCAL_REPOSITORY"
    authority_layer: str | None = None
    authority_effect: KnowledgeAuthorityEffect | None = None
    authority_scope: str | None = None
    observed_expected_layer: str = "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    authority_basis: tuple[str, ...] = ()
    action: str = "NO_CHANGE"
    result: str = "COMPLIANT"
    proposed_path: str | None = None
    source_of_truth: bool = False
    machine_enforceable: bool = False
    audit_required: bool = False
    classification: KnowledgeClassification = KnowledgeClassification.INTERNAL

    def __post_init__(self) -> None:
        _require_non_empty("artifact_id", self.artifact_id)
        _require_non_empty("domain", self.domain)
        _require_non_empty("owner", self.owner)
        _require_non_empty("canonical_path", self.canonical_path)
        _require_non_empty("filename", self.filename)
        if "\\" in self.canonical_path or self.canonical_path.startswith("/"):
            raise ValueError("canonical_path must be repository-relative posix path")
        if self.sensitive and self.checksum is not None:
            raise ValueError("sensitive repository artifacts must not be hashed")
        if self.size < 0:
            raise ValueError("artifact size cannot be negative")
        if not isinstance(self.source_of_truth, bool):
            raise ValueError("source_of_truth must be boolean")
        if not isinstance(self.machine_enforceable, bool):
            raise ValueError("machine_enforceable must be boolean")
        if not isinstance(self.audit_required, bool):
            raise ValueError("audit_required must be boolean")
        if not isinstance(self.classification, KnowledgeClassification):
            raise ValueError(
                "classification must use the canonical knowledge classification"
            )
        if self.authority_layer is not None and (
            self.authority_layer not in _REPOSITORY_AUTHORITY_LAYERS
        ):
            raise ValueError("authority_layer must use the canonical authority pyramid")
        if self.authority_effect is not None and not isinstance(
            self.authority_effect,
            KnowledgeAuthorityEffect,
        ):
            raise ValueError(
                "authority_effect must use the canonical authority effects"
            )
        if self.authority_scope is not None:
            if not self.authority_scope.strip():
                raise ValueError("authority_scope cannot be empty")
            if _AUTHORITY_SCOPE_RE.match(self.authority_scope) is None:
                raise ValueError(
                    "authority_scope must use lower_snake_case semantic scope naming"
                )
        if self.observed_expected_layer not in _REPOSITORY_AUTHORITY_LAYERS:
            raise ValueError(
                "observed_expected_layer must use the canonical authority pyramid"
            )
        _require_unique_nonblank("authority_basis", self.authority_basis)


@dataclass(frozen=True, slots=True)
class GovernedKnowledgeObject:
    """Machine-readable contract for authoritative system knowledge."""

    knowledge_id: str
    knowledge_type: KnowledgeObjectType
    title: str
    version: str
    lifecycle_status: KnowledgeLifecycleStatus
    authority_level: KnowledgeAuthorityLevel
    authority_layer: str
    authority_effect: KnowledgeAuthorityEffect | None
    content_role: KnowledgeContentRole
    owner: str
    source_of_truth: bool
    machine_enforceable: bool
    audit_required: bool
    classification: KnowledgeClassification
    path: str
    canonical_path: str
    authority_scope: str | None = None
    source_of_truth_scope: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("knowledge_id", self.knowledge_id)
        _require_non_empty("knowledge title", self.title)
        _require_non_empty("knowledge version", self.version)
        _require_non_empty("knowledge owner", self.owner)
        _require_non_empty("knowledge path", self.path)
        _require_non_empty("knowledge canonical_path", self.canonical_path)
        if "\\" in self.canonical_path or self.canonical_path.startswith("/"):
            raise ValueError(
                "knowledge canonical_path must be repository-relative posix path"
            )
        if self.canonical_path != self.path:
            raise ValueError(
                "knowledge canonical_path must match repository-relative path"
            )
        if not _KNOWLEDGE_ID_RE.match(self.knowledge_id):
            raise ValueError("knowledge_id must match AI4B-<DOMAIN>-<TYPE>-<NUMBER>")
        if not _SEMVER_RE.match(self.version):
            raise ValueError("knowledge version must be semantic MAJOR.MINOR.PATCH")
        if self.authority_layer not in _REPOSITORY_AUTHORITY_LAYERS:
            raise ValueError(
                "knowledge authority_layer must use the canonical authority pyramid"
            )
        if self.authority_scope is None:
            raise ValueError("authority_scope is required")
        if not self.authority_scope.strip():
            raise ValueError("authority_scope cannot be empty")
        if _AUTHORITY_SCOPE_RE.match(self.authority_scope) is None:
            raise ValueError(
                "authority_scope must use lower_snake_case semantic scope naming"
            )
        if (
            self.authority_effect is KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION
            and self.source_of_truth
            and self.authority_scope is None
        ):
            raise ValueError(
                "operational specialization knowledge must declare authority_scope"
            )
        if self.content_role is KnowledgeContentRole.AUTHORITATIVE and (
            not self.source_of_truth
        ):
            raise ValueError("authoritative knowledge must be source_of_truth=true")
        if (
            self.source_of_truth_scope is not None
            and not self.source_of_truth_scope.strip()
        ):
            raise ValueError("source_of_truth_scope cannot be empty")
        if self.source_of_truth and self.content_role not in {
            KnowledgeContentRole.AUTHORITATIVE,
            KnowledgeContentRole.OPERATIONAL,
            KnowledgeContentRole.POLICY_AS_CODE,
        }:
            raise ValueError(
                "source_of_truth=true requires content_role=AUTHORITATIVE "
                "or OPERATIONAL or POLICY_AS_CODE"
            )
        if self.classification is KnowledgeClassification.SECRET:
            raise ValueError("secret values must not be governed as documentation")


@dataclass(frozen=True, slots=True)
class GovernedDocumentLockEntry:
    """Registration and integrity baseline for one governed Markdown document."""

    path: str
    canonical_path: str
    authority_level: str
    document_status: str
    version: str
    expected_hash: str
    source_of_truth: bool
    supersedes: tuple[str, ...]
    allowed_change_process: str
    authority_layer: str | None = None
    authority_effect: str | None = None
    authority_scope: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorityEvidence:
    """Validated evidence used to assign governance authority layers."""

    metadata: GovernedKnowledgeObject | None
    registered_policy: bool
    canonical_path_verified: bool
    downstream_usage_count: int


@dataclass(frozen=True, slots=True)
class RepositoryValidationFinding:
    kind: RepositoryFindingKind
    severity: RepositoryFindingSeverity
    path: str
    detail: str
    blocker: bool
    control_family: RepositoryControlFamily | None = None
    domain: str = ""
    rule_id: str = ""
    finding_id: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("finding path", self.path)
        _require_non_empty("finding detail", self.detail)
        if self.control_family is None:
            object.__setattr__(self, "control_family", _control_family(self.kind))
        if not self.domain:
            object.__setattr__(self, "domain", _domain(self.path))
        else:
            _require_non_empty("finding domain", self.domain)
        if not self.rule_id:
            object.__setattr__(self, "rule_id", _rule_id(self.kind))
        else:
            _require_non_empty("finding rule_id", self.rule_id)
        if not self.finding_id:
            object.__setattr__(
                self,
                "finding_id",
                _deterministic_finding_id(self.kind, self.path),
            )
        else:
            _require_non_empty("finding_id", self.finding_id)


@dataclass(frozen=True, slots=True)
class RepositoryRemediationAction:
    """Deterministic repair recommendation derived from a repository finding."""

    action_id: str
    finding_kind: RepositoryFindingKind
    action_type: str
    current_path: str
    proposed_path: str | None
    reason: str
    destructive: bool
    requires_approval: bool
    evidence_required: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty("action_id", self.action_id)
        _require_non_empty("action_type", self.action_type)
        _require_non_empty("current_path", self.current_path)
        _require_non_empty("remediation reason", self.reason)
        _require_unique_nonblank("evidence_required", self.evidence_required)


@dataclass(frozen=True, slots=True)
class RepositoryValidationReport:
    policy_id: str
    policy_version: str
    repository_root: str
    analyzed_at_utc: str
    status: RepositoryValidationStatus
    artifact_count: int
    governed_knowledge_count: int
    artifacts: tuple[RepositoryArtifact, ...]
    findings: tuple[RepositoryValidationFinding, ...]
    recommended_actions: tuple[RepositoryRemediationAction, ...]
    blockers: tuple[str, ...]
    repository_health_score: int
    analysis_scope: str = "AGGRESSIVE_ALL_FILES"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    policy_source_path: str = "IN_MEMORY"

    def __post_init__(self) -> None:
        _require_non_empty("policy_id", self.policy_id)
        _require_non_empty("policy_version", self.policy_version)
        _require_non_empty("policy_source_path", self.policy_source_path)
        _require_non_empty("repository_root", self.repository_root)
        _require_non_empty("analyzed_at_utc", self.analyzed_at_utc)
        _require_non_empty("analysis_scope", self.analysis_scope)
        _require_unique_nonblank("validation blockers", self.blockers)
        if self.status is RepositoryValidationStatus.PASS and self.blockers:
            raise ValueError("passing repository validation cannot contain blockers")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("repository validation cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("repository validation cannot authorize live trading")
        if not 0 <= self.repository_health_score <= 100:
            raise ValueError("repository_health_score must be 0..100")

    def to_payload(self) -> dict[str, object]:
        payload = to_primitive(self)
        if not isinstance(payload, dict):
            raise RuntimeError("REPOSITORY_VALIDATION_PAYLOAD_INVALID")
        payload["allowed_results"] = _allowed_artifact_results()
        payload["result_counts"] = _result_counts(self.artifacts)
        payload["migration_map"] = _migration_map_payload(
            self.artifacts, self.recommended_actions
        )
        payload["dashboard_metrics"] = _dashboard_metrics(self)
        payload["root_inventory"] = _root_inventory_payload(self.artifacts)
        return payload


def validate_repository(
    repository_root: Path,
    *,
    policy: RepositoryPolicy | None = None,
    policy_source_path: Path | None = None,
) -> RepositoryValidationReport:
    """Validate repository file governance without mutating the workspace."""
    root = repository_root.resolve()
    if not root.is_dir():
        raise ValueError("repository_root must be an existing directory")
    resolved_policy_path = (
        policy_source_path
        if policy_source_path is not None
        else root / REPOSITORY_VALIDATOR_POLICY_PATH
    )
    if policy is not None:
        active_policy = policy
    elif resolved_policy_path.is_file():
        active_policy = load_repository_policy(resolved_policy_path)
    else:
        active_policy = RepositoryPolicy.ai4binance_vnext()
    tracked_files = _git_tracked_files(root)
    repository_files = tuple(_repository_files(root, active_policy))
    authority_index = _authority_index(root, active_policy, repository_files)
    artifacts = tuple(
        _iter_artifacts(
            root,
            active_policy,
            tracked_files,
            repository_files,
            authority_index,
        )
    )
    findings = tuple(_findings(root, active_policy, artifacts))
    recommended_actions = tuple(_recommended_actions(findings))
    blockers = tuple(
        dict.fromkeys(
            _finding_blocker_id(finding) for finding in findings if finding.blocker
        )
    )
    score = _health_score(findings)
    return RepositoryValidationReport(
        policy_id=active_policy.policy_id,
        policy_version=active_policy.version,
        policy_source_path=_policy_source_path_label(
            root, resolved_policy_path, policy
        ),
        repository_root=str(root),
        status=(
            RepositoryValidationStatus.PASS
            if not blockers
            else RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
        ),
        artifact_count=len(artifacts),
        governed_knowledge_count=_governed_knowledge_count(root, active_policy),
        analyzed_at_utc=datetime.now(UTC).isoformat(),
        artifacts=artifacts,
        findings=findings,
        recommended_actions=recommended_actions,
        blockers=blockers,
        repository_health_score=score,
    )


def load_repository_mirror_policy(path: Path) -> RepositoryMirrorPolicy:
    """Load and validate the repository mirror policy YAML contract."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mirror policy must be a mapping")
    canonical = payload.get("canonical_repository", {})
    mirror = payload.get("mirror", {})
    sync = payload.get("sync", {})
    exclusions = payload.get("exclusions", {})
    retention = payload.get("retention", {})
    if not isinstance(canonical, dict):
        raise ValueError("canonical_repository must be a mapping")
    if not isinstance(mirror, dict):
        raise ValueError("mirror must be a mapping")
    if canonical.get("authority") != "AUTHORITATIVE":
        raise ValueError("canonical repository must remain authoritative")
    return RepositoryMirrorPolicy(
        policy_id=_yaml_string(payload, "policy_id"),
        version=_yaml_string(payload, "version"),
        status=_yaml_string(payload, "status"),
        mirror_role=_yaml_string(mirror, "role"),
        mirror_authority=_yaml_string(mirror, "authority"),
        may_be_source_of_truth=_yaml_bool(mirror, "may_be_source_of_truth"),
        may_override_canonical=_yaml_bool(mirror, "may_override_canonical"),
        default_action=_yaml_string(sync, "default_action"),
        allowed_exact_paths=_yaml_string_tuple(sync, "allowed_exact_paths"),
        allowed_prefixes=_yaml_string_tuple(sync, "allowed_prefixes"),
        selective_prefixes=_yaml_string_tuple(retention, "selective_prefixes"),
        hard_exclude_patterns=_yaml_string_tuple(exclusions, "hard_exclude_patterns"),
        private_patterns=_yaml_string_tuple(exclusions, "private_patterns"),
        local_only_prefixes=_yaml_string_tuple(exclusions, "local_only_prefixes"),
        never_mirror_prefixes=_yaml_string_tuple(exclusions, "never_mirror_prefixes"),
    )


def load_repository_policy(path: Path) -> RepositoryPolicy:
    """Load and validate the repository validator policy JSON contract."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("repository validator policy must be a mapping")
    section_requirements = payload.get("knowledge_section_requirements", {})
    if not isinstance(section_requirements, dict):
        raise ValueError("knowledge_section_requirements must be a mapping")
    return RepositoryPolicy(
        policy_id=_json_string(payload, "policy_id"),
        version=_json_string(payload, "version"),
        allowed_top_level_paths=_json_string_tuple(payload, "allowed_top_level_paths"),
        source_roots=_json_string_tuple(payload, "source_roots"),
        test_roots=_json_string_tuple(payload, "test_roots"),
        docs_roots=_json_string_tuple(payload, "docs_roots"),
        generated_roots=_json_string_tuple(payload, "generated_roots"),
        protected_roots=_json_string_tuple(payload, "protected_roots"),
        ignored_parts=_json_string_tuple(payload, "ignored_parts"),
        cache_parts=_json_string_tuple(payload, "cache_parts"),
        legacy_path_targets=_json_string_mapping(payload, "legacy_path_targets"),
        forbidden_python_filenames=_json_string_tuple(
            payload, "forbidden_python_filenames"
        ),
        allowed_absolute_path_literals=_json_string_tuple(
            payload, "allowed_absolute_path_literals", allow_empty=True
        ),
        knowledge_metadata_required_paths=_json_string_tuple(
            payload, "knowledge_metadata_required_paths"
        ),
        english_only_knowledge_paths=_json_string_tuple(
            payload, "english_only_knowledge_paths"
        ),
        non_code_content_language=_json_string(payload, "non_code_content_language"),
        knowledge_section_requirements={
            _normalize_repository_policy_path(str(key)): _json_string_sequence(
                value,
                f"knowledge_section_requirements.{key}",
                normalize_paths=False,
            )
            for key, value in section_requirements.items()
        },
        owner_by_top_level=_json_string_mapping(
            payload,
            "owner_by_top_level",
            normalize_values=False,
        ),
        compatibility_imports=_json_string_tuple_mapping(
            payload,
            "compatibility_imports",
        ),
    )


def validate_mirror_hygiene(
    mirror_manifest: Path,
    *,
    policy: RepositoryMirrorPolicy | None = None,
) -> MirrorHygieneReport:
    """Validate a mirror inventory manifest without mutating local or cloud files."""
    active_policy = policy or RepositoryMirrorPolicy.ai4binance_vnext()
    manifest_path = mirror_manifest.resolve()
    if not manifest_path.is_file():
        raise ValueError("mirror_manifest must be an existing file")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = tuple(_mirror_inventory_entries(payload))
    findings = tuple(_mirror_findings(payload, entries, active_policy))
    cleanup_plan = tuple(_mirror_cleanup_plan(entries, findings, active_policy))
    blockers = tuple(
        dict.fromkeys(
            _finding_blocker_id(finding) for finding in findings if finding.blocker
        )
    )
    return MirrorHygieneReport(
        policy_id=active_policy.policy_id,
        policy_version=active_policy.version,
        mirror_manifest_path=str(manifest_path),
        analyzed_at_utc=datetime.now(UTC).isoformat(),
        status=(
            RepositoryValidationStatus.PASS
            if not blockers
            else RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
        ),
        mirror_role=active_policy.mirror_role,
        mirror_authority=active_policy.mirror_authority,
        mirror_source_of_truth=False,
        entry_count=len(entries),
        findings=findings,
        cleanup_plan=cleanup_plan,
        blockers=blockers,
        dashboard_metrics=_mirror_dashboard_metrics(entries, findings, cleanup_plan),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI4BINANCE deterministic repository governance validator"
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--check-repository",
        action="store_true",
        help="Validate canonical repository governance. This is the default mode.",
    )
    parser.add_argument(
        "--check-mirror-manifest",
        type=Path,
        help="Validate a non-authoritative mirror inventory manifest.",
    )
    parser.add_argument(
        "--mirror-policy",
        type=Path,
        help="Repository-relative or absolute mirror hygiene policy YAML.",
    )
    parser.add_argument(
        "--repository-policy",
        type=Path,
        help="Repository-relative or absolute repository validator policy JSON.",
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--output-migration-map", type=Path)
    parser.add_argument("--output-findings-json", type=Path)
    parser.add_argument("--output-policy-snapshot", type=Path)
    parser.add_argument("--output-cleanup-plan", type=Path)
    parser.add_argument("--output-mirror-manifest", type=Path)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write requested report files without printing the full JSON payload.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.check_mirror_manifest is not None:
        policy_path = (
            parsed.mirror_policy
            if parsed.mirror_policy is not None
            else parsed.repository_root / REPOSITORY_MIRROR_POLICY_PATH
        )
        mirror_policy = load_repository_mirror_policy(policy_path)
        mirror_report = validate_mirror_hygiene(
            parsed.check_mirror_manifest,
            policy=mirror_policy,
        )
        if parsed.output_json is not None:
            _write_mirror_report_json(parsed.output_json, mirror_report)
        if parsed.output_markdown is not None:
            _write_mirror_report_markdown(parsed.output_markdown, mirror_report)
        if parsed.output_cleanup_plan is not None:
            _write_mirror_cleanup_plan(parsed.output_cleanup_plan, mirror_report)
        if not parsed.quiet:
            print(
                json.dumps(
                    mirror_report.to_payload(), ensure_ascii=True, sort_keys=True
                )
            )
        return 0 if mirror_report.status is RepositoryValidationStatus.PASS else 2

    repository_policy_path = (
        parsed.repository_policy
        if parsed.repository_policy is not None
        else parsed.repository_root / REPOSITORY_VALIDATOR_POLICY_PATH
    )
    repository_policy = (
        load_repository_policy(repository_policy_path)
        if repository_policy_path.is_file()
        else RepositoryPolicy.ai4binance_vnext()
    )
    repository_report = validate_repository(
        parsed.repository_root,
        policy=repository_policy,
        policy_source_path=repository_policy_path,
    )
    if parsed.output_json is not None:
        _write_report_json(parsed.output_json, repository_report)
    if parsed.output_markdown is not None:
        _write_report_markdown(parsed.output_markdown, repository_report)
    if parsed.output_migration_map is not None:
        _write_migration_map_markdown(parsed.output_migration_map, repository_report)
    if parsed.output_findings_json is not None:
        _write_findings_json(parsed.output_findings_json, repository_report)
    if parsed.output_policy_snapshot is not None:
        _write_policy_snapshot_json(
            parsed.output_policy_snapshot,
            repository_report,
            repository_policy,
        )
    if parsed.output_mirror_manifest is not None:
        mirror_policy_path = (
            parsed.mirror_policy
            if parsed.mirror_policy is not None
            else parsed.repository_root / REPOSITORY_MIRROR_POLICY_PATH
        )
        mirror_policy = (
            load_repository_mirror_policy(mirror_policy_path)
            if mirror_policy_path.is_file()
            else RepositoryMirrorPolicy.ai4binance_vnext()
        )
        _write_mirror_manifest_json(
            parsed.output_mirror_manifest,
            repository_report,
            policy=mirror_policy,
        )
    if not parsed.quiet:
        print(
            json.dumps(
                repository_report.to_payload(), ensure_ascii=True, sort_keys=True
            )
        )
    return 0 if repository_report.status is RepositoryValidationStatus.PASS else 2


def _yaml_string(payload: dict[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _json_string(payload: dict[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _json_string_sequence(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
    normalize_paths: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} entries must be non-empty strings")
        items.append(
            _normalize_repository_policy_path(item) if normalize_paths else item.strip()
        )
    if not allow_empty and not items:
        raise ValueError(f"{label} must not be empty")
    return tuple(items)


def _json_string_tuple(
    payload: dict[object, object],
    key: str,
    *,
    allow_empty: bool = False,
    normalize_paths: bool = True,
) -> tuple[str, ...]:
    return _json_string_sequence(
        payload.get(key),
        key,
        allow_empty=allow_empty,
        normalize_paths=normalize_paths,
    )


def _json_string_mapping(
    payload: dict[object, object],
    key: str,
    *,
    normalize_keys: bool = True,
    normalize_values: bool = True,
) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(f"{key} keys must be non-empty strings")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{key} values must be non-empty strings")
        normalized[
            _normalize_repository_policy_path(raw_key)
            if normalize_keys
            else raw_key.strip()
        ] = (
            _normalize_repository_policy_path(raw_value)
            if normalize_values
            else raw_value.strip()
        )
    return normalized


def _json_string_tuple_mapping(
    payload: dict[object, object],
    key: str,
) -> dict[str, tuple[str, ...]]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(f"{key} keys must be non-empty strings")
        normalized[raw_key.strip()] = _json_string_sequence(
            raw_value,
            f"{key}.{raw_key}",
            normalize_paths=False,
        )
    return normalized


def _validate_compatibility_imports(
    compatibility_imports: dict[str, tuple[str, ...]],
) -> None:
    for source_module, targets in compatibility_imports.items():
        _require_non_empty("compatibility import source", source_module)
        _require_unique_nonblank(
            f"compatibility_imports[{source_module}]",
            targets,
        )
        source_layer = _canonical_layer_for_module(source_module)
        if source_layer not in {"application", "compatibility"}:
            raise ValueError(
                "compatibility import sources must belong to application or "
                "compatibility"
            )
        for target_module in targets:
            _require_non_empty("compatibility import target", target_module)
            if not target_module.startswith("ai4binance."):
                raise ValueError(
                    "compatibility import targets must be ai4binance modules"
                )
            target_layer = _canonical_layer_for_module(target_module)
            if source_layer == "application" and target_layer != "compatibility":
                raise ValueError(
                    "application compatibility imports must target compatibility"
                )
            if source_layer == "compatibility" and target_layer is not None:
                raise ValueError(
                    "compatibility implementations may list only legacy imports"
                )


def _normalize_repository_policy_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if not normalized:
        raise ValueError("repository validator policy path entry must be non-empty")
    return normalized.rstrip("/")


def _policy_source_path_label(
    root: Path,
    policy_source_path: Path,
    policy: RepositoryPolicy | None,
) -> str:
    if policy is not None and not policy_source_path.is_file():
        return "IN_MEMORY"
    try:
        return policy_source_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(policy_source_path.resolve())


def _yaml_bool(payload: dict[object, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _yaml_string_tuple(payload: dict[object, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} entries must be non-empty strings")
        items.append(_normalize_mirror_path(item))
    return tuple(items)


def _mirror_inventory_entries(payload: object) -> Iterable[MirrorInventoryEntry]:
    raw_entries: Sequence[object]
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = _mirror_manifest_entry_values(payload)
    else:
        raise ValueError("mirror inventory manifest must be a list or mapping")
    for raw_entry in raw_entries:
        yield _mirror_inventory_entry(raw_entry)


def _mirror_manifest_entry_values(payload: dict[object, object]) -> Sequence[object]:
    for key in ("entries", "files", "artifacts", "root_inventory", "paths"):
        value = payload.get(key)
        if value is not None:
            if not isinstance(value, list):
                raise ValueError(f"mirror manifest {key} must be a list")
            return value
    raise ValueError("mirror manifest must contain entries, files, artifacts or paths")


def _mirror_inventory_entry(raw_entry: object) -> MirrorInventoryEntry:
    if isinstance(raw_entry, str):
        return MirrorInventoryEntry(path=_normalize_mirror_path(raw_entry))
    if not isinstance(raw_entry, dict):
        raise ValueError("mirror inventory entries must be strings or mappings")
    path = raw_entry.get("path") or raw_entry.get("source_path")
    path = path or raw_entry.get("canonical_path")
    if not isinstance(path, str):
        raise ValueError("mirror inventory entry path must be a string")
    source_of_truth = raw_entry.get("source_of_truth", False)
    if not isinstance(source_of_truth, bool):
        raise ValueError("mirror inventory entry source_of_truth must be boolean")
    authority = raw_entry.get("authority")
    if authority is not None and not isinstance(authority, str):
        raise ValueError("mirror inventory entry authority must be a string")
    git_tracked = raw_entry.get("git_tracked")
    if git_tracked is not None and not isinstance(git_tracked, bool):
        raise ValueError("mirror inventory entry git_tracked must be boolean")
    return MirrorInventoryEntry(
        path=_normalize_mirror_path(path),
        source_of_truth=source_of_truth,
        authority=authority,
        git_tracked=git_tracked,
    )


def _normalize_mirror_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if not normalized or normalized == "." or ".." in Path(normalized).parts:
        raise ValueError("mirror path must be repository-relative")
    return normalized.rstrip("/")


def _mirror_findings(
    payload: object,
    entries: tuple[MirrorInventoryEntry, ...],
    policy: RepositoryMirrorPolicy,
) -> Iterable[RepositoryValidationFinding]:
    yield from _mirror_manifest_authority_findings(payload)
    for entry in entries:
        classification = _mirror_path_classification(entry.path, policy)
        finding = _mirror_path_finding(entry.path, classification)
        if finding is not None:
            yield finding
        if entry.source_of_truth or _is_authoritative_mirror_authority(entry.authority):
            yield _blocker(
                RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION,
                entry.path,
                "Mirror inventory entry declares repository authority.",
            )


def _mirror_manifest_authority_findings(
    payload: object,
) -> Iterable[RepositoryValidationFinding]:
    if not isinstance(payload, dict):
        return
    if payload.get("source_of_truth") is True:
        yield _blocker(
            RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION,
            "__manifest__",
            "Mirror manifest declares source_of_truth=true.",
        )
    authority = payload.get("authority")
    if isinstance(authority, str) and _is_authoritative_mirror_authority(authority):
        yield _blocker(
            RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION,
            "__manifest__",
            "Mirror manifest declares repository authority.",
        )


def _is_authoritative_mirror_authority(authority: str | None) -> bool:
    if authority is None:
        return False
    return authority.upper() not in {"NONE", "BACKUP_ONLY", "EVIDENCE_MIRROR"}


def _mirror_path_finding(
    relative: str,
    classification: MirrorPathClassification,
) -> RepositoryValidationFinding | None:
    finding_map = {
        MirrorPathClassification.SCM_INTERNAL: (
            RepositoryFindingKind.MIRROR_FORBIDDEN_PATH,
            "SCM internals must never be replicated into repository mirrors.",
        ),
        MirrorPathClassification.CACHE: (
            RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
            "Development cache output is not mirror-retained evidence.",
        ),
        MirrorPathClassification.TEST_CACHE: (
            RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
            "Test cache output is not mirror-retained evidence.",
        ),
        MirrorPathClassification.TEST_TEMP: (
            RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
            "Temporary test output must not be mirrored.",
        ),
        MirrorPathClassification.GENERATED: (
            RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT,
            "Generated Python/build output must not be mirrored as source.",
        ),
        MirrorPathClassification.PRIVATE: (
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION,
            "Private repository evidence must remain local-only.",
        ),
        MirrorPathClassification.SECRET: (
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION,
            "Secret-bearing files must never be mirrored.",
        ),
        MirrorPathClassification.RUNTIME_STATE: (
            RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
            "Runtime state is local-only by default.",
        ),
        MirrorPathClassification.RUNTIME_DATA: (
            RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
            "Runtime data is local-only by default.",
        ),
        MirrorPathClassification.RUNTIME_LOG: (
            RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
            "Routine logs are local-only by default.",
        ),
        MirrorPathClassification.TEMP: (
            RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
            "Temporary runtime output must not be mirrored.",
        ),
        MirrorPathClassification.UNKNOWN: (
            RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
            "Mirror path is not explicitly allowlisted or classified.",
        ),
    }
    mapped = finding_map.get(classification)
    if mapped is None:
        return None
    kind, detail = mapped
    return _blocker(kind, relative, detail)


def _mirror_path_classification(
    relative: str,
    policy: RepositoryMirrorPolicy,
) -> MirrorPathClassification:
    if relative == ".env.example":
        return MirrorPathClassification.CONFIG
    if _matches_mirror_pattern(relative, (".git", ".git/**")):
        return MirrorPathClassification.SCM_INTERNAL
    if _matches_mirror_pattern(relative, policy.private_patterns):
        if relative == ".env.example":
            return MirrorPathClassification.CONFIG
        return (
            MirrorPathClassification.SECRET
            if relative.startswith(".env") or "secret" in relative.lower()
            else MirrorPathClassification.PRIVATE
        )
    if _is_under(relative, policy.never_mirror_prefixes):
        if relative.startswith("artifacts/test_temp"):
            return MirrorPathClassification.TEST_TEMP
        return MirrorPathClassification.TEMP
    parts = set(Path(relative).parts)
    suffix = Path(relative).suffix.lower()
    if "__pycache__" in parts or suffix in {".pyc", ".pyo"}:
        return MirrorPathClassification.GENERATED
    if relative.endswith(".egg-info") or ".egg-info/" in relative:
        return MirrorPathClassification.GENERATED
    if _matches_mirror_pattern(relative, policy.hard_exclude_patterns):
        return _hard_exclude_classification(relative)
    if _is_under(relative, policy.local_only_prefixes):
        if relative.startswith("runtime/data"):
            return MirrorPathClassification.RUNTIME_DATA
        if relative.startswith(("logs", "runtime/logs")):
            return MirrorPathClassification.RUNTIME_LOG
        return MirrorPathClassification.RUNTIME_STATE
    if relative in policy.allowed_exact_paths:
        return _allowed_exact_classification(relative)
    if _is_under(relative, policy.selective_prefixes):
        return _selective_prefix_classification(relative)
    if _is_under(relative, policy.allowed_prefixes):
        return _allowed_prefix_classification(relative)
    return MirrorPathClassification.UNKNOWN


def _hard_exclude_classification(relative: str) -> MirrorPathClassification:
    path_parts = Path(relative).parts
    parts = set(path_parts)
    suffix = Path(relative).suffix.lower()
    if ".hypothesis" in parts or ".pytest_cache" in parts:
        return MirrorPathClassification.TEST_CACHE
    if (
        ".pytest-tmp" in parts
        or any(
            part.startswith(".pytest-basetemp") or part.startswith("pytest-basetemp")
            for part in path_parts
        )
        or any(
            part.startswith(".pytest-audit-temp")
            or part.startswith(".pytest-money-audit-")
            for part in path_parts
        )
        or relative in {"runtime/pytest-temp", "runtime/pytest-tmp"}
        or relative.startswith("runtime/pytest-temp/")
        or relative.startswith("runtime/pytest-tmp/")
        or path_parts[:3] == ("runtime", "tmp", "pytest")
    ):
        return MirrorPathClassification.TEST_TEMP
    if "__pycache__" in parts or suffix in {".pyc", ".pyo"}:
        return MirrorPathClassification.GENERATED
    if relative.endswith(".egg-info") or ".egg-info/" in relative:
        return MirrorPathClassification.GENERATED
    return MirrorPathClassification.CACHE


def _allowed_exact_classification(relative: str) -> MirrorPathClassification:
    if relative == ".env.example":
        return MirrorPathClassification.CONFIG
    if Path(relative).suffix.lower() in {".toml", ".lock"} or relative.startswith("."):
        return MirrorPathClassification.CONFIG
    return MirrorPathClassification.GOVERNED_KNOWLEDGE


def _selective_prefix_classification(relative: str) -> MirrorPathClassification:
    if relative.startswith("runtime/reports"):
        return MirrorPathClassification.REPORT
    if relative.startswith("runtime/artifacts/quality/gate"):
        return MirrorPathClassification.SELECTIVE_ARCHIVE
    return MirrorPathClassification.AUDIT_EVIDENCE


def _allowed_prefix_classification(relative: str) -> MirrorPathClassification:
    if relative.startswith("src/"):
        return MirrorPathClassification.SOURCE
    if relative.startswith("tests/"):
        return MirrorPathClassification.TEST
    if relative.startswith("docs/"):
        return MirrorPathClassification.GOVERNED_KNOWLEDGE
    if relative.startswith("schemas/"):
        return MirrorPathClassification.CONTRACT
    if relative.startswith("config/"):
        return MirrorPathClassification.CONFIG
    if relative.startswith("migrations/"):
        return MirrorPathClassification.MIGRATION
    if relative.startswith("tools/"):
        return MirrorPathClassification.TOOLING
    return MirrorPathClassification.OPERATIONAL_SURFACE


def _matches_mirror_pattern(relative: str, patterns: tuple[str, ...]) -> bool:
    lowered = relative.lower()
    for pattern in patterns:
        normalized = pattern.lower()
        if fnmatch.fnmatchcase(lowered, normalized):
            return True
        if normalized.endswith("/**"):
            prefix = normalized.removesuffix("/**")
            if lowered == prefix or lowered.startswith(prefix + "/"):
                return True
    return False


def _mirror_cleanup_plan(
    entries: tuple[MirrorInventoryEntry, ...],
    findings: tuple[RepositoryValidationFinding, ...],
    policy: RepositoryMirrorPolicy,
) -> Iterable[MirrorCleanupPlanEntry]:
    finding_paths = {
        finding.path for finding in findings if finding.path != "__manifest__"
    }
    for entry in entries:
        classification = _mirror_path_classification(entry.path, policy)
        if entry.path not in finding_paths:
            action = MirrorCleanupAction.KEEP_IN_MIRROR
            local_action = "KEEP_CANONICAL"
            risk = "LOW"
            approval_required = False
        elif classification is MirrorPathClassification.UNKNOWN:
            action = MirrorCleanupAction.QUARANTINE_FOR_REVIEW
            local_action = "KEEP_UNTIL_CLASSIFIED"
            risk = "MEDIUM"
            approval_required = True
        elif classification in {
            MirrorPathClassification.PRIVATE,
            MirrorPathClassification.SECRET,
        }:
            action = MirrorCleanupAction.QUARANTINE_FOR_REVIEW
            local_action = "KEEP_LOCAL_ONLY"
            risk = "HIGH"
            approval_required = True
        else:
            action = MirrorCleanupAction.REMOVE_FROM_MIRROR
            local_action = "KEEP_OR_REGENERATE"
            risk = "LOW"
            approval_required = False
        yield MirrorCleanupPlanEntry(
            path=entry.path,
            classification=classification,
            canonical_required=_mirror_canonical_required(classification),
            mirror_action=action,
            local_action=local_action,
            risk=risk,
            approval_required=approval_required,
        )


def _mirror_canonical_required(classification: MirrorPathClassification) -> bool:
    return classification in {
        MirrorPathClassification.SOURCE,
        MirrorPathClassification.TEST,
        MirrorPathClassification.GOVERNED_KNOWLEDGE,
        MirrorPathClassification.CONFIG,
        MirrorPathClassification.CONTRACT,
        MirrorPathClassification.OPERATIONAL_SURFACE,
        MirrorPathClassification.MIGRATION,
        MirrorPathClassification.TOOLING,
        MirrorPathClassification.AUDIT_EVIDENCE,
        MirrorPathClassification.REPORT,
        MirrorPathClassification.SELECTIVE_ARCHIVE,
    }


def _mirror_dashboard_metrics(
    entries: tuple[MirrorInventoryEntry, ...],
    findings: tuple[RepositoryValidationFinding, ...],
    cleanup_plan: tuple[MirrorCleanupPlanEntry, ...],
) -> dict[str, int | float]:
    finding_kinds = [finding.kind for finding in findings]
    pollution_entries = [
        entry
        for entry in cleanup_plan
        if entry.mirror_action is not MirrorCleanupAction.KEEP_IN_MIRROR
    ]
    tracked_pollution = [
        entry
        for entry in entries
        if entry.git_tracked
        and any(plan.path == entry.path for plan in pollution_entries)
    ]
    noise_ratio = round(len(pollution_entries) / len(entries), 4) if entries else 0.0
    return {
        "mirrored_git_internal_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_FORBIDDEN_PATH
        ),
        "mirrored_cache_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_CACHE_POLLUTION
        ),
        "mirrored_runtime_pollution_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION
        ),
        "mirrored_private_evidence_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION
        ),
        "mirrored_generated_artifact_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT
        ),
        "unknown_mirror_classification_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_UNKNOWN_PATH
        ),
        "source_of_truth_violation_count": finding_kinds.count(
            RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION
        ),
        "filesystem_pollution_count": len(pollution_entries),
        "tracked_pollution_count": len(tracked_pollution),
        "mirror_cleanup_destructive_unknowns": sum(
            1
            for entry in cleanup_plan
            if entry.classification is MirrorPathClassification.UNKNOWN
            and entry.mirror_action is MirrorCleanupAction.REMOVE_FROM_MIRROR
        ),
        "mirror_noise_ratio": noise_ratio,
    }


def _iter_artifacts(
    root: Path,
    policy: RepositoryPolicy,
    tracked_files: set[str],
    repository_files: tuple[Path, ...],
    authority_index: dict[str, AuthorityEvidence],
) -> Iterable[RepositoryArtifact]:
    for path in repository_files:
        relative = _relative(path, root)
        artifact_type = _artifact_type(relative, policy)
        authority_evidence = authority_index[relative]
        sensitive = _is_sensitive(relative, policy)
        proposed_path = _proposed_artifact_path(relative, policy)
        action = _artifact_action(relative, artifact_type, proposed_path)
        stat = path.stat()
        artifact_id = str(uuid5(NAMESPACE_URL, f"ai4binance:{relative}"))
        yield RepositoryArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            artifact_class=_artifact_class(relative, artifact_type),
            domain=_domain(relative),
            owner=_owner(relative, policy),
            canonical_path=relative,
            filename=path.name,
            schema_version=None,
            lifecycle_status=RepositoryArtifactLifecycle.ACTIVE,
            generated=_is_generated_artifact(relative, policy),
            immutable=_is_immutable(relative, artifact_type),
            sensitive=sensitive,
            git_tracked=relative in tracked_files,
            checksum=None if sensitive else _sha256(path),
            file_id=artifact_id,
            path=relative,
            mime_type=_mime_type(path),
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            authority_layer=_artifact_authority_layer(authority_evidence),
            authority_effect=(
                authority_evidence.metadata.authority_effect
                if authority_evidence.metadata is not None
                else None
            ),
            authority_scope=(
                authority_evidence.metadata.authority_scope
                if authority_evidence.metadata is not None
                else None
            ),
            observed_expected_layer=_observed_expected_layer(relative, artifact_type),
            authority_basis=_authority_basis(
                authority_evidence,
                observed_expected_layer=_observed_expected_layer(
                    relative,
                    artifact_type,
                ),
            ),
            action=action,
            result=_artifact_result(action),
            proposed_path=proposed_path,
            source_of_truth=(
                authority_evidence.metadata.source_of_truth
                if authority_evidence.metadata is not None
                else False
            ),
            machine_enforceable=(
                authority_evidence.metadata.machine_enforceable
                if authority_evidence.metadata is not None
                else False
            ),
            audit_required=(
                authority_evidence.metadata.audit_required
                if authority_evidence.metadata is not None
                else False
            ),
            classification=(
                authority_evidence.metadata.classification
                if authority_evidence.metadata is not None
                else (
                    KnowledgeClassification.RESTRICTED
                    if sensitive
                    else KnowledgeClassification.INTERNAL
                )
            ),
        )


def _repository_files(root: Path, policy: RepositoryPolicy) -> Iterable[Path]:
    """Yield repository files while pruning policy-ignored directory trees.

    ``Path.rglob`` enumerated every file before applying the ignore policy.
    Runtime evidence and tool payloads are already non-authoritative, so
    enumerating them first only adds latency and memory pressure.  Traversal
    remains deterministic, and ``src`` stays inspectable for explicit
    generated/runtime artifact findings.
    """

    for directory, dirnames, filenames in os.walk(root, topdown=True):
        directory_path = Path(directory)
        retained_dirnames: list[str] = []
        for dirname in sorted(dirnames):
            candidate = directory_path / dirname
            relative = _relative(candidate, root)
            if _is_under_src(relative) or not _is_ignored(candidate, root, policy):
                retained_dirnames.append(dirname)
        dirnames[:] = retained_dirnames

        for filename in sorted(filenames):
            path = directory_path / filename
            relative = _relative(path, root)
            if relative == BLOCKER_REGISTRY_PATH.as_posix():
                continue
            if (
                _is_source_generated_artifact(relative)
                or _is_source_runtime_artifact(relative)
                or not _is_ignored(path, root, policy)
            ):
                yield path


def _authority_index(
    root: Path,
    policy: RepositoryPolicy,
    repository_files: tuple[Path, ...],
) -> dict[str, AuthorityEvidence]:
    relatives = tuple(_relative(path, root) for path in repository_files)
    metadata_by_path = _authority_metadata_by_path(root, relatives)
    downstream_usage = _downstream_usage_counts(root, repository_files, relatives)
    registered_paths = set(policy.knowledge_metadata_required_paths)
    index: dict[str, AuthorityEvidence] = {}
    for relative in relatives:
        metadata = metadata_by_path.get(relative)
        index[relative] = AuthorityEvidence(
            metadata=metadata,
            registered_policy=relative in registered_paths,
            canonical_path_verified=(
                metadata is None or metadata.canonical_path == relative
            ),
            downstream_usage_count=downstream_usage.get(relative, 0),
        )
    return index


def _authority_metadata_by_path(
    root: Path,
    relatives: tuple[str, ...],
) -> dict[str, GovernedKnowledgeObject]:
    objects: dict[str, GovernedKnowledgeObject] = {}
    for relative in relatives:
        path = root / relative
        if path.suffix.lower() != ".md":
            continue
        metadata = _frontmatter(path)
        if metadata is None:
            continue
        if any(
            not metadata.get(field, "").strip()
            for field in _required_knowledge_fields()
        ):
            continue
        if _required_explicit_authority_fields(relative, metadata):
            continue
        try:
            objects[relative] = _knowledge_object(relative, metadata)
        except ValueError:
            continue
    return objects


def _downstream_usage_counts(
    root: Path,
    repository_files: tuple[Path, ...],
    relatives: tuple[str, ...],
) -> dict[str, int]:
    counts = dict.fromkeys(relatives, 0)
    target_set = set(relatives)
    for path in repository_files:
        if not _is_text_reference_candidate(path):
            continue
        source_relative = _relative(path, root)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for target in target_set:
            if target != source_relative and target in text:
                counts[target] += 1
    return counts


def _is_text_reference_candidate(path: Path) -> bool:
    return path.suffix.lower() in {
        ".cfg",
        ".ini",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }


def _findings(
    root: Path,
    policy: RepositoryPolicy,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    yield from _top_level_findings(root, policy)
    yield from _blocker_registry_findings(root)
    yield from _authority_graph_findings(root)
    yield from _governance_enforcement_fabric_findings(root, policy, artifacts)
    yield from _knowledge_findings(root, policy)
    yield from _non_code_content_language_findings(root, policy, artifacts)
    yield from _canonical_import_boundary_findings(root, policy, artifacts)
    yield from _canonical_ownership_findings(root, artifacts)
    for artifact in artifacts:
        yield from _artifact_findings(root, policy, artifact, include_naming=False)


def _governance_enforcement_fabric_findings(
    root: Path,
    policy: RepositoryPolicy,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    for artifact in artifacts:
        yield from _naming_findings(root, policy, artifact)
    required_paths = (
        GOVERNANCE_ENFORCEMENT_FABRIC_PATH,
        GOVERNANCE_ENFORCEMENT_FABRIC_SCHEMA_PATH,
        Path("config/governance/canonical_terminology_registry.yaml"),
        Path("schemas/governance/canonical_terminology_registry.schema.json"),
        TECHNOLOGY_LANGUAGE_STANDARD_PATH,
        TECHNOLOGY_LANGUAGE_POLICY_PATH,
        TECHNOLOGY_LANGUAGE_SCHEMA_PATH,
    )
    if not any((root / path).is_file() for path in required_paths):
        return
    entries, _, lock_error = _document_lock_manifest(root)
    if lock_error is not None:
        yield _blocker(
            RepositoryFindingKind.GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION,
            GOVERNANCE_ENFORCEMENT_FABRIC_PATH.as_posix(),
            "Governance enforcement fabric cannot read the document lock: "
            f"{lock_error}",
        )
        return
    try:
        fabric = load_governance_enforcement_fabric(root)
    except ValueError as exc:
        yield _blocker(
            RepositoryFindingKind.GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION,
            GOVERNANCE_ENFORCEMENT_FABRIC_PATH.as_posix(),
            f"Governance enforcement fabric failed validation: {exc}",
        )
        return
    lock_hashes = {path: entry.expected_hash for path, entry in entries.items()}
    for violation in evaluate_governance_enforcement_fabric(
        root,
        fabric,
        (artifact.path for artifact in artifacts),
        lock_hashes,
    ):
        kind = _fabric_finding_kind(violation.family, violation.code)
        detail = f"{violation.code}: {violation.detail}"
        if violation.blocker:
            yield _blocker(kind, violation.path, detail)
        else:
            yield RepositoryValidationFinding(
                kind=kind,
                severity=RepositoryFindingSeverity.WARNING,
                path=violation.path,
                detail=detail,
                blocker=False,
            )


def _fabric_finding_kind(family: str, code: str) -> RepositoryFindingKind:
    if family == "technology_language":
        return RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION
    if family == "terminology":
        if code == "TERMINOLOGY_PROHIBITED_TERM":
            return RepositoryFindingKind.TERMINOLOGY_PROHIBITED_TERM
        if code == "TERMINOLOGY_DEPRECATED_ALIAS":
            return RepositoryFindingKind.TERMINOLOGY_DEPRECATED_ALIAS
        return RepositoryFindingKind.TERMINOLOGY_POLICY_VIOLATION
    return RepositoryFindingKind.GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION


def _blocker_registry_findings(root: Path) -> Iterable[RepositoryValidationFinding]:
    relative = BLOCKER_REGISTRY_PATH.as_posix()
    path = root / BLOCKER_REGISTRY_PATH
    if not path.is_file():
        yield _blocker(
            RepositoryFindingKind.BLOCKER_REGISTRY_INVALID,
            relative,
            "Canonical blocker registry is missing.",
        )
        return
    try:
        load_blocker_registry(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        yield _blocker(
            RepositoryFindingKind.BLOCKER_REGISTRY_INVALID,
            relative,
            f"Canonical blocker registry failed validation: {exc}",
        )


def _technology_language_policy_findings(
    root: Path,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    required_paths = (
        TECHNOLOGY_LANGUAGE_STANDARD_PATH,
        TECHNOLOGY_LANGUAGE_POLICY_PATH,
        TECHNOLOGY_LANGUAGE_SCHEMA_PATH,
    )
    present = tuple((root / path).is_file() for path in required_paths)
    if not any(present):
        return
    missing = tuple(
        path.as_posix()
        for path, is_present in zip(required_paths, present, strict=True)
        if not is_present
    )
    if missing:
        yield _blocker(
            RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION,
            TECHNOLOGY_LANGUAGE_POLICY_PATH.as_posix(),
            "Technology language enforcement chain is incomplete: "
            + ", ".join(missing)
            + ".",
        )
        return
    try:
        policy = load_technology_language_policy(root)
        violations = evaluate_technology_language_policy(
            root,
            policy,
            (artifact.path for artifact in artifacts),
        )
    except ValueError as exc:
        yield _blocker(
            RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION,
            TECHNOLOGY_LANGUAGE_POLICY_PATH.as_posix(),
            f"Technology language policy failed validation: {exc}",
        )
        return
    for violation in violations:
        yield _blocker(
            RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION,
            violation.path,
            f"{violation.code}: {violation.detail}",
        )


def _authority_graph_findings(root: Path) -> Iterable[RepositoryValidationFinding]:
    registry_path = root / AUTHORITY_GRAPH_REGISTRY_PATH
    if not registry_path.is_file():
        return
    try:
        graph = load_authority_graph(
            registry_path,
            schema_root=root / "schemas",
        )
    except ValueError as error:
        yield _blocker(
            RepositoryFindingKind.AUTHORITY_GRAPH_INVALID,
            AUTHORITY_GRAPH_REGISTRY_PATH,
            f"Authority graph registry failed validation: {error}",
        )
        return
    for conflict in detect_authority_conflicts(graph):
        path = _authority_graph_conflict_path(graph, conflict.node_ids)
        yield _blocker(
            RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT,
            path,
            f"{conflict.kind.value}: {conflict.detail}",
        )
    try:
        development_matrix = load_authority_layer_development_matrix(root)
    except ValueError as error:
        yield _blocker(
            RepositoryFindingKind.AUTHORITY_GRAPH_INVALID,
            "config/governance/authority_layer_development_matrix.yaml",
            f"Authority development matrix failed validation: {error}",
        )
        return
    for development_finding in validate_authority_graph_layer_development(
        graph, development_matrix
    ):
        yield _blocker(
            RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT,
            development_finding.path,
            f"{development_finding.code}: {development_finding.detail}",
        )
    for metadata_finding in validate_authority_graph_metadata(graph, root):
        yield _blocker(
            RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT,
            metadata_finding.path,
            (
                f"{metadata_finding.kind.value}:{metadata_finding.field}: "
                f"{metadata_finding.detail}"
            ),
        )


def _authority_graph_conflict_path(graph: object, node_ids: tuple[str, ...]) -> str:
    from ai4binance.governance.authority.graph import AuthorityGraph

    if not isinstance(graph, AuthorityGraph):
        return AUTHORITY_GRAPH_REGISTRY_PATH
    nodes = {node.node_id: node for node in graph.nodes}
    for node_id in node_ids:
        node = nodes.get(node_id)
        if node is not None:
            return node.canonical_path
    return AUTHORITY_GRAPH_REGISTRY_PATH


def _top_level_findings(
    root: Path, policy: RepositoryPolicy
) -> Iterable[RepositoryValidationFinding]:
    allowed = _registered_top_level_paths(policy)
    for path in sorted(root.iterdir()):
        name = path.name
        if name == ".git" or name in allowed or name in set(policy.ignored_parts):
            continue
        if name in _LEGACY_RUNTIME_ROOT_TARGETS and _has_material_contents(path):
            target = _LEGACY_RUNTIME_ROOT_TARGETS[name]
            yield _blocker(
                RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE,
                name,
                f"Legacy runtime output path must move under {target}.",
            )
            continue
        yield RepositoryValidationFinding(
            kind=RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
            severity=RepositoryFindingSeverity.WARNING,
            path=name,
            detail="Top-level path is not registered in RepositoryPolicy.",
            blocker=False,
        )
    for required_name in (*CANONICAL_ROOT_FILES, *CANONICAL_TOP_LEVEL_PATHS):
        if not (root / required_name).exists():
            yield RepositoryValidationFinding(
                kind=RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
                severity=RepositoryFindingSeverity.WARNING,
                path=required_name,
                detail=(
                    "Canonical repository tree path is absent. Create it only "
                    "when it can be tracked without moving protected runtime "
                    "state or generated evidence without approval."
                ),
                blocker=False,
            )


def _has_material_contents(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir():
        return any(candidate.is_file() for candidate in path.rglob("*"))
    return path.exists()


def _artifact_findings(
    root: Path,
    policy: RepositoryPolicy,
    artifact: RepositoryArtifact,
    *,
    include_naming: bool = True,
) -> Iterable[RepositoryValidationFinding]:
    relative = artifact.canonical_path
    path = root / relative
    if include_naming:
        yield from _naming_findings(root, policy, artifact)
    if _is_under_src(relative):
        relative_parts = Path(relative).parts
        if _is_source_generated_artifact(relative) or any(
            part.lower() in {"reports", "artifacts", "logs"} for part in relative_parts
        ):
            yield _blocker(
                RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC,
                relative,
                "Generated artifact/report/log folder must not live under src.",
            )
        if _is_source_runtime_artifact(relative):
            yield _blocker(
                RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC,
                relative,
                "Runtime state must not live under src.",
            )
        if path.suffix == ".py":
            yield from _absolute_path_findings(path, root, policy)


def _naming_findings(
    root: Path,
    policy: RepositoryPolicy,
    artifact: RepositoryArtifact,
) -> Iterable[RepositoryValidationFinding]:
    relative = artifact.canonical_path
    path = root / relative
    if _is_under(relative, policy.source_roots) and path.suffix == ".py":
        if not _PYTHON_FILE_RE.match(path.name):
            yield _blocker(
                RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION,
                relative,
                "Python source files must use lower_snake_case.py.",
            )
        if path.name in set(policy.forbidden_python_filenames):
            yield _blocker(
                RepositoryFindingKind.FORBIDDEN_SOURCE_FILENAME,
                relative,
                "Source filename is ambiguous or discouraged by RepositoryPolicy.",
            )
        if _SOURCE_VERSION_RE.search(path.name):
            yield _blocker(
                RepositoryFindingKind.SOURCE_VERSION_FILENAME,
                relative,
                "Source filename must not substitute for Git/version metadata.",
            )
        for parent in path.relative_to(root / "src" / "ai4binance").parents:
            if str(parent) == ".":
                continue
            for part in parent.parts:
                if part == "__pycache__":
                    continue
                if not _LOWER_SNAKE_RE.match(part):
                    yield _blocker(
                        RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION,
                        relative,
                        f"Python package folder is not lower_snake_case: {part}",
                    )


def _canonical_import_boundary_findings(
    root: Path,
    policy: RepositoryPolicy,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    for artifact in artifacts:
        relative = artifact.canonical_path
        if not relative.endswith(".py"):
            continue
        source_layer = _canonical_layer_for_relative(relative)
        if source_layer is None or source_layer == "cli":
            continue
        module_name = _module_name_for_relative(relative)
        if module_name is None:
            continue
        path = root / relative
        text = path.read_text(encoding="utf-8")
        try:
            import_targets = tuple(
                _import_targets_for_module(text, module_name, relative)
            )
        except (SyntaxError, ValueError) as exc:
            yield _blocker(
                RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION,
                relative,
                f"Canonical import-boundary scan failed closed: {exc}.",
            )
            continue
        allowed_layers = _CANONICAL_LAYER_ALLOWED_DEPENDENCIES[source_layer]
        explicitly_allowed = policy.compatibility_imports.get(module_name, ())
        violations: list[str] = []
        for target in import_targets:
            if not target.startswith("ai4binance."):
                continue
            target_layer = _canonical_layer_for_module(target)
            is_compatibility_facade_import = (
                source_layer == "application"
                and target_layer == "compatibility"
                and target in explicitly_allowed
            )
            is_approved_legacy_import = (
                source_layer == "compatibility"
                and target_layer is None
                and target in explicitly_allowed
            )
            if (
                target_layer not in allowed_layers
                and not is_compatibility_facade_import
                and not is_approved_legacy_import
            ):
                violations.append(
                    f"{target} ({target_layer or 'non_canonical_ai4binance'})"
                )
        if not violations:
            continue
        allowed_summary = ", ".join(sorted(allowed_layers))
        violation_summary = ", ".join(dict.fromkeys(violations))
        yield _blocker(
            RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION,
            relative,
            (
                f"Canonical layer '{source_layer}' may depend only on "
                f"{allowed_summary}; found {violation_summary}."
            ),
        )


def _canonical_ownership_findings(
    root: Path,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    artifact_paths = {artifact.canonical_path for artifact in artifacts}
    opportunities_relative = "src/ai4binance/opportunities.py"
    if opportunities_relative in artifact_paths:
        opportunities_path = root / opportunities_relative
        if _is_opportunity_module_ownership_ambiguous(opportunities_path):
            yield _blocker(
                RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY,
                opportunities_relative,
                (
                    "Module mixes domain opportunity observation contracts, "
                    "application inbox assembly, and local artifact I/O; "
                    "canonical ownership is ambiguous until responsibilities "
                    "are split or relocated."
                ),
            )
    radar_relative = "src/ai4binance/opportunity_radar.py"
    if radar_relative in artifact_paths:
        radar_path = root / radar_relative
        if _is_opportunity_radar_ownership_ambiguous(radar_path):
            yield _blocker(
                RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY,
                radar_relative,
                (
                    "Module mixes application radar assembly with local "
                    "artifact persistence; canonical ownership is ambiguous "
                    "until builder and persistence responsibilities are split."
                ),
            )


def _is_opportunity_module_ownership_ambiguous(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    domain_markers = {
        "VWAPOpportunity",
        "VWAPOpportunityConfig",
        "VWAPOpportunityEvaluator",
    }
    application_markers = {
        "OpportunityInbox",
        "OpportunityInboxItem",
        "OpportunityInboxBuilder",
    }
    has_domain_contracts = bool(class_names & domain_markers)
    has_application_assembly = bool(class_names & application_markers)
    has_local_artifact_io = ".read_text(" in text and "json.loads(" in text
    return has_domain_contracts and has_application_assembly and has_local_artifact_io


def _is_opportunity_radar_ownership_ambiguous(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    has_builder = "build_opportunity_radar_snapshot" in function_names
    has_persistence = "write_opportunity_radar_snapshot" in function_names
    has_local_artifact_io = ".write_text(" in text
    return has_builder and has_persistence and has_local_artifact_io


def _canonical_layer_for_relative(relative: str) -> str | None:
    module_name = _module_name_for_relative(relative)
    if module_name is None:
        return None
    return _canonical_layer_for_module(module_name)


def _canonical_layer_for_module(module_name: str) -> str | None:
    for layer, prefix in _CANONICAL_LAYER_PREFIXES:
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            return layer
    return None


def _module_name_for_relative(relative: str) -> str | None:
    path = Path(relative)
    parts = path.parts
    if len(parts) < 3 or parts[0] != "src" or parts[1] != "ai4binance":
        return None
    if path.name == "__init__.py":
        return ".".join(parts[1:-1])
    return ".".join((*parts[1:-1], path.stem))


def _import_targets_for_module(
    text: str,
    module_name: str,
    relative: str,
) -> Iterable[str]:
    tree = ast.parse(text)
    package_name = module_name if relative.endswith("/__init__.py") else ""
    if not package_name:
        package_name = module_name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            if node.module:
                if node.module == "ai4binance":
                    for alias in node.names:
                        yield f"ai4binance.{alias.name}"
                else:
                    yield node.module
            continue
        if not package_name:
            raise ValueError(
                "relative import cannot be resolved without a containing package"
            )
        relative_name = "." * node.level + (node.module or "")
        yield importlib.util.resolve_name(relative_name, package_name)


def _knowledge_findings(
    root: Path,
    policy: RepositoryPolicy,
) -> Iterable[RepositoryValidationFinding]:
    objects: list[GovernedKnowledgeObject] = []
    required_paths = set(policy.knowledge_metadata_required_paths)
    knowledge_paths = tuple(
        dict.fromkeys(
            (
                *policy.knowledge_metadata_required_paths,
                *_governed_markdown_knowledge_paths(root),
            )
        )
    )
    for relative in knowledge_paths:
        path = root / relative
        if not path.is_file():
            if relative not in required_paths:
                continue
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
                relative,
                "Required governed knowledge document is missing.",
            )
            continue
        metadata = _frontmatter(path)
        if metadata is None:
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
                relative,
                "Governed knowledge document must start with metadata frontmatter.",
            )
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_markdown_heading(text, "ELI10"):
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING,
                relative,
                "Governed Markdown knowledge document must include an ELI10 section.",
            )
        missing = [
            field
            for field in _required_knowledge_fields()
            if _required_knowledge_field_missing(field, metadata)
        ]
        missing.extend(_required_explicit_authority_fields(relative, metadata))
        if missing:
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
                relative,
                f"Governed knowledge metadata missing fields: {', '.join(missing)}.",
            )
            continue
        expected_scopes = _expected_source_of_truth_scopes(relative, metadata)
        actual_scope = metadata.get("source_of_truth_scope")
        if expected_scopes:
            if not actual_scope:
                yield _blocker(
                    RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
                    relative,
                    (
                        "Governed knowledge metadata missing fields: "
                        "source_of_truth_scope."
                    ),
                )
                continue
            if actual_scope not in expected_scopes:
                expected_scope_detail = (
                    expected_scopes[0]
                    if len(expected_scopes) == 1
                    else f"one of: {', '.join(expected_scopes)}"
                )
                yield _blocker(
                    RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
                    relative,
                    (
                        "Governed knowledge source_of_truth_scope must be "
                        f"{expected_scope_detail}."
                    ),
                )
                continue
        yield from _knowledge_lifecycle_findings(relative, metadata, text)
        try:
            objects.append(_knowledge_object(relative, metadata))
        except ValueError as exc:
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
                relative,
                str(exc),
            )
    yield from _knowledge_required_section_findings(root, policy)
    yield from _english_only_knowledge_findings(root, policy)
    seen: dict[str, str] = {}
    for knowledge_object in objects:
        previous = seen.get(knowledge_object.knowledge_id)
        if previous is None:
            seen[knowledge_object.knowledge_id] = knowledge_object.path
            continue
        yield _blocker(
            RepositoryFindingKind.KNOWLEDGE_ID_DUPLICATE,
            knowledge_object.path,
            (
                "knowledge_id must be globally unique; duplicate also found at "
                f"{previous}."
            ),
        )
    yield from _source_of_truth_conflict_findings(objects)
    yield from _authority_scope_override_conflict_findings(objects)
    yield from _source_of_truth_filename_case_findings(objects)
    yield from _governed_document_lock_findings(root, objects)
    yield from _runtime_markdown_authority_findings(root)
    yield from _noncanonical_operational_markdown_authority_findings(root)


def _knowledge_lifecycle_findings(
    relative: str,
    metadata: dict[str, str],
    text: str,
) -> Iterable[RepositoryValidationFinding]:
    if _knowledge_lifecycle_status_conflict(metadata):
        yield _blocker(
            RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION,
            relative,
            _knowledge_lifecycle_alias_message(
                "Governed knowledge metadata lifecycle_status must match status "
                "when both are present."
            ),
        )
    status = _knowledge_lifecycle_status(metadata)
    is_active = status == KnowledgeLifecycleStatus.ACTIVE.value
    if (
        _metadata_bool("source_of_truth", metadata)
        or _metadata_bool("machine_enforceable", metadata)
    ) and not is_active:
        yield _blocker(
            RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION,
            relative,
            _knowledge_lifecycle_alias_message(
                "Source-of-truth or machine-enforceable governed knowledge "
                "must have ACTIVE lifecycle status."
            ),
        )
    if (
        metadata.get("document_type", "").strip() == KnowledgeObjectType.REGISTRY.value
        and not is_active
        and _registry_has_active_entries(text)
    ):
        yield _blocker(
            RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION,
            relative,
            "DRAFT registry documents cannot contain ACTIVE registry entries.",
        )


def _knowledge_lifecycle_status(metadata: dict[str, str]) -> str:
    canonical_status = metadata.get("lifecycle_status", "").strip()
    legacy_status = metadata.get("status", "").strip()
    if canonical_status:
        return canonical_status
    return legacy_status


def _knowledge_lifecycle_status_conflict(metadata: dict[str, str]) -> bool:
    canonical_status = metadata.get("lifecycle_status", "").strip()
    legacy_status = metadata.get("status", "").strip()
    return bool(
        canonical_status and legacy_status and legacy_status != canonical_status
    )


def _knowledge_lifecycle_alias_message(message: str) -> str:
    return (
        f"{message} Use lifecycle_status as the canonical field; "
        "status is the frontmatter alias."
    )


def _registry_has_active_entries(text: str) -> bool:
    return any(
        line.lstrip().startswith("|")
        and "| ACTIVE |" in line
        and "lifecycle_status" not in line
        for line in text.splitlines()
    )


def _governed_markdown_knowledge_paths(root: Path) -> tuple[str, ...]:
    """Return existing permanent Markdown knowledge surfaces to validate."""
    candidates: list[Path] = []
    docs_root = root / "docs"
    if docs_root.is_dir():
        candidates.extend(docs_root.rglob("*.md"))
    candidates.extend(_repository_named_files(root, "AGENTS.md"))
    candidates.extend(
        root / relative
        for relative in (
            "README.md",
            "CLAUDE.md",
            "GEMINI.md",
            "docs/providers/instruction_codex_provider.md",
            "docs/governance/instruction_core_custom_instructions.md",
            (
                "docs/standards/"
                "standard_engineering_python_clean_code_vscode_development.md"
            ),
            *GOVERNED_OPERATIONAL_EXCEPTION_MARKDOWN_PATHS,
        )
    )
    return tuple(
        sorted(
            {
                _relative(path, root)
                for path in candidates
                if path.is_file()
                and not any(
                    part.startswith(".") for part in path.relative_to(root).parts
                )
                and not _is_ignored(path, root, RepositoryPolicy.ai4binance_vnext())
            }
        )
    )


def _repository_named_files(root: Path, filename: str) -> tuple[Path, ...]:
    """Find named repository files without descending into ignored runtime trees."""

    policy = RepositoryPolicy.ai4binance_vnext()
    matches: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True):
        directory_path = Path(directory)
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _is_ignored(directory_path / dirname, root, policy)
        ]
        if filename in filenames:
            matches.append(directory_path / filename)
    return tuple(matches)


def _runtime_markdown_authority_findings(
    root: Path,
) -> Iterable[RepositoryValidationFinding]:
    runtime_root = root / "runtime"
    if not runtime_root.is_dir():
        return
    authoritative_roles = {"AUTHORITATIVE", "POLICY_AS_CODE"}
    forbidden_authorities = {
        KnowledgeAuthorityLevel.REPOSITORY.value,
        KnowledgeAuthorityLevel.ENFORCEABLE.value,
        KnowledgeAuthorityLevel.NORMATIVE.value,
        KnowledgeAuthorityLevel.PROVIDER_ADAPTER.value,
        KnowledgeAuthorityLevel.EXTERNAL_AUTHORITY.value,
    }
    for path in _runtime_markdown_paths(root):
        if not path.is_file():
            continue
        relative = _relative(path, root)
        if (
            _is_runtime_test_temp_path(relative)
            or _is_runtime_maintenance_archive_path(relative)
            or _is_runtime_vnext_worktree_path(relative)
        ):
            continue
        if _read_utf8_text_or_none(path) is None:
            yield _blocker(
                RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION,
                relative,
                "Non-code repository content must be UTF-8 English text.",
            )
            continue
        metadata = _frontmatter(path)
        if metadata is None:
            continue
        if metadata.get("source_of_truth", "").strip().lower() == "true":
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                "Generated runtime Markdown must not declare source_of_truth=true.",
            )
        if metadata.get("source_of_truth_scope", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                "Generated runtime Markdown must not declare source_of_truth_scope.",
            )
        if metadata.get("authority_layer", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                "Generated runtime Markdown must not declare authority_layer.",
            )
        if metadata.get("authority_scope", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                "Generated runtime Markdown must not declare authority_scope.",
            )
        if metadata.get("authority_effect", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                "Generated runtime Markdown must not declare authority_effect.",
            )
        authority_level = metadata.get("authority_level", "").strip()
        if authority_level in forbidden_authorities:
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Generated runtime Markdown must not declare a canonical "
                    f"authority level: {authority_level}."
                ),
            )
        content_role = metadata.get("content_role", "").strip()
        if content_role in authoritative_roles:
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Generated runtime Markdown must not declare a canonical "
                    f"content_role: {content_role}."
                ),
            )


def _runtime_markdown_paths(root: Path) -> tuple[Path, ...]:
    """Return runtime Markdown while pruning non-authoritative heavy subtrees."""

    runtime_root = root / "runtime"
    if not runtime_root.is_dir():
        return ()
    paths: list[Path] = []
    for directory, dirnames, filenames in os.walk(runtime_root, topdown=True):
        directory_path = Path(directory)
        retained: list[str] = []
        for dirname in sorted(dirnames):
            relative = _relative(directory_path / dirname, root)
            if (
                _is_runtime_test_temp_path(relative)
                or _is_runtime_maintenance_archive_path(relative)
                or _is_runtime_vnext_worktree_path(relative)
            ):
                continue
            retained.append(dirname)
        dirnames[:] = retained
        paths.extend(
            directory_path / filename
            for filename in sorted(filenames)
            if filename.lower().endswith(".md")
        )
    return tuple(paths)


def _noncanonical_operational_markdown_authority_findings(
    root: Path,
) -> Iterable[RepositoryValidationFinding]:
    authoritative_roles = {"AUTHORITATIVE", "POLICY_AS_CODE"}
    forbidden_authorities = {
        KnowledgeAuthorityLevel.REPOSITORY.value,
        KnowledgeAuthorityLevel.ENFORCEABLE.value,
        KnowledgeAuthorityLevel.NORMATIVE.value,
        KnowledgeAuthorityLevel.PROVIDER_ADAPTER.value,
        KnowledgeAuthorityLevel.EXTERNAL_AUTHORITY.value,
    }
    for relative in NONCANONICAL_OPERATIONAL_MARKDOWN_PATHS:
        path = root / relative
        if not path.is_file():
            continue
        if _read_utf8_text_or_none(path) is None:
            yield _blocker(
                RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION,
                relative,
                "Non-code repository content must be UTF-8 English text.",
            )
            continue
        metadata = _frontmatter(path)
        if metadata is None:
            continue
        if metadata.get("source_of_truth", "").strip().lower() == "true":
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare "
                    "source_of_truth=true."
                ),
            )
        if metadata.get("source_of_truth_scope", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare "
                    "source_of_truth_scope."
                ),
            )
        if metadata.get("authority_layer", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare "
                    "authority_layer."
                ),
            )
        if metadata.get("authority_scope", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare "
                    "authority_scope."
                ),
            )
        if metadata.get("authority_effect", "").strip():
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare "
                    "authority_effect."
                ),
            )
        authority_level = metadata.get("authority_level", "").strip()
        if authority_level in forbidden_authorities:
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare a "
                    f"canonical authority level: {authority_level}."
                ),
            )
        content_role = metadata.get("content_role", "").strip()
        if content_role in authoritative_roles:
            yield _blocker(
                RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
                relative,
                (
                    "Non-canonical operational Markdown must not declare a "
                    f"canonical content_role: {content_role}."
                ),
            )


def _is_runtime_test_temp_path(relative: str) -> bool:
    path_parts = Path(relative).parts
    return path_parts[:3] in {
        ("runtime", "tmp", "process"),
        ("runtime", "tmp", "pytest"),
        ("runtime", "tmp", "test_temp"),
    }


def _is_runtime_maintenance_archive_path(relative: str) -> bool:
    path_parts = Path(relative).parts
    return path_parts[:3] == ("runtime", "artifacts", "maintenance_archive")


def _is_runtime_vnext_worktree_path(relative: str) -> bool:
    path_parts = Path(relative).parts
    return path_parts[:3] == ("runtime", "tmp", "vnext_worktrees")


def _expected_source_of_truth_scopes(
    relative: str,
    metadata: dict[str, str],
) -> tuple[str, ...]:
    operational_scope = _expected_operational_source_of_truth_scope(relative, metadata)
    if operational_scope is not None:
        return (operational_scope,)
    if relative in _FAMILY_INDEX_KNOWLEDGE_PATHS:
        return ("family_index",)
    expected_scopes: list[str] = []
    authority_scope = metadata.get("authority_scope", "").strip()
    if authority_scope and (
        relative in _PROVIDER_ADAPTER_KNOWLEDGE_PATHS
        or _metadata_bool("source_of_truth", metadata)
    ):
        expected_scopes.append(authority_scope)
    if relative in _PROVIDER_ADAPTER_KNOWLEDGE_PATHS:
        expected_scopes.append("provider_adapter")
    if _metadata_bool("source_of_truth", metadata):
        expected_scopes.append("canonical")
    return tuple(dict.fromkeys(expected_scopes))


def _expected_operational_source_of_truth_scope(
    relative: str,
    metadata: dict[str, str],
) -> str | None:
    if not _requires_explicit_operational_authority_metadata(relative, metadata):
        return None
    authority_scope = metadata.get("authority_scope", "").strip()
    if not authority_scope:
        return None
    if relative.startswith("docs/workflows/"):
        return f"{authority_scope}_workflow"
    if relative.startswith("docs/procedures/"):
        return f"{authority_scope}_procedure"
    if relative.startswith("docs/runbooks/"):
        return f"{authority_scope}_runbook"
    return None


def _requires_explicit_operational_authority_metadata(
    relative: str,
    metadata: dict[str, str],
) -> bool:
    return _metadata_bool("source_of_truth", metadata) and relative.startswith(
        _OPERATIONAL_AUTHORITY_METADATA_PREFIXES
    )


def _normalize_authority_effect(value: str) -> KnowledgeAuthorityEffect:
    normalized = value.strip()
    if not normalized:
        raise ValueError("authority_effect cannot be empty")
    try:
        return KnowledgeAuthorityEffect(normalized)
    except ValueError:
        alias = _LEGACY_AUTHORITY_EFFECT_ALIASES.get(normalized)
        if alias is not None:
            return alias
        raise ValueError(
            "authority_effect must use the canonical authority effect taxonomy"
        ) from None


def _source_of_truth_conflict_findings(
    objects: list[GovernedKnowledgeObject],
) -> Iterable[RepositoryValidationFinding]:
    seen: dict[tuple[KnowledgeObjectType, str], GovernedKnowledgeObject] = {}
    for knowledge_object in objects:
        if (
            not knowledge_object.source_of_truth
            or knowledge_object.lifecycle_status is not KnowledgeLifecycleStatus.ACTIVE
        ):
            continue
        key = (
            knowledge_object.knowledge_type,
            _normalize_title(knowledge_object.title),
        )
        previous = seen.get(key)
        if previous is None:
            seen[key] = knowledge_object
            continue
        yield _blocker(
            RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT,
            knowledge_object.path,
            (
                "Only one active source-of-truth may define the same knowledge "
                f"concept; duplicate also found at {previous.path}."
            ),
        )


def _authority_scope_override_conflict_findings(
    objects: list[GovernedKnowledgeObject],
) -> Iterable[RepositoryValidationFinding]:
    concept_groups: dict[str, list[GovernedKnowledgeObject]] = defaultdict(list)
    for knowledge_object in objects:
        if (
            knowledge_object.lifecycle_status is not KnowledgeLifecycleStatus.ACTIVE
            or knowledge_object.authority_scope is None
            or knowledge_object.authority_effect
            in {
                KnowledgeAuthorityEffect.EVIDENCE_ONLY,
                KnowledgeAuthorityEffect.REFERENCE_ONLY,
                KnowledgeAuthorityEffect.ARCHIVE_ONLY,
            }
        ):
            continue
        concept_groups[knowledge_object.authority_scope].append(knowledge_object)
    for authority_scope, concept_objects in concept_groups.items():
        if len(concept_objects) < 2:
            continue
        ranked_objects = sorted(
            concept_objects,
            key=lambda item: (_authority_layer_rank(item.authority_layer), item.path),
        )
        canonical_owner = ranked_objects[0]
        owner_rank = _authority_layer_rank(canonical_owner.authority_layer)
        for knowledge_object in ranked_objects[1:]:
            if _authority_layer_rank(knowledge_object.authority_layer) == owner_rank:
                continue
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT,
                knowledge_object.path,
                _authority_scope_override_message(
                    authority_scope=authority_scope,
                    canonical_owner=canonical_owner,
                    conflicting_object=knowledge_object,
                ),
            )


def _authority_layer_rank(authority_layer: str) -> int:
    return _REPOSITORY_AUTHORITY_LAYERS.index(authority_layer)


def _authority_scope_override_message(
    *,
    authority_scope: str,
    canonical_owner: GovernedKnowledgeObject,
    conflicting_object: GovernedKnowledgeObject,
) -> str:
    return (
        "A lower-authority governed object cannot weaken, contradict, override, "
        "or silently co-own a higher-authority concept. "
        f"authority_scope={authority_scope!r} is already owned by "
        f"{canonical_owner.authority_layer} at {canonical_owner.path}; "
        f"{conflicting_object.authority_layer} at {conflicting_object.path} must "
        "use a narrower derived authority_scope/source_of_truth_scope instead of "
        "reusing the higher-authority concept owner scope."
    )


def _source_of_truth_filename_case_findings(
    objects: list[GovernedKnowledgeObject],
) -> Iterable[RepositoryValidationFinding]:
    reserved_conventional_filenames = {"AGENTS.md", "README.md"}
    for knowledge_object in objects:
        if (
            not knowledge_object.source_of_truth
            or knowledge_object.lifecycle_status is not KnowledgeLifecycleStatus.ACTIVE
        ):
            continue
        path = Path(knowledge_object.path)
        if path.name in reserved_conventional_filenames:
            continue
        if any(character.isupper() for character in path.name):
            yield _blocker(
                RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION,
                knowledge_object.path,
                (
                    "Active source-of-truth filenames must be lower-case; "
                    "reserved conventional exceptions are "
                    f"{', '.join(reserved_conventional_filenames)}."
                ),
            )


def _governed_document_lock_findings(
    root: Path,
    objects: list[GovernedKnowledgeObject],
) -> Iterable[RepositoryValidationFinding]:
    locked_objects = tuple(
        knowledge_object
        for knowledge_object in objects
        if _requires_governed_document_lock(knowledge_object)
    )
    if not locked_objects:
        return
    lock_manifest_path = root / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    if not _git_has_head(root) and not lock_manifest_path.is_file():
        return
    locked_paths = {knowledge_object.path for knowledge_object in locked_objects}
    manifest_entries, approvals, manifest_error = _document_lock_manifest(root)
    if manifest_error is not None:
        yield _blocker(
            RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
            GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH,
            manifest_error,
        )
        return
    for extra_path in sorted(set(manifest_entries) - locked_paths):
        yield _blocker(
            RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
            extra_path,
            (
                "Locked document manifest contains a path that is no longer an "
                "active source-of-truth or machine-enforceable governed document."
            ),
        )
    for knowledge_object in locked_objects:
        path = root / knowledge_object.path
        lock_entry = manifest_entries.get(knowledge_object.path)
        if lock_entry is None:
            yield _blocker(
                RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
                knowledge_object.path,
                (
                    "Active source-of-truth, policy-as-code, or "
                    "machine-enforceable governed document is not registered "
                    "in the document lock manifest."
                ),
            )
            continue
        registration_error = _document_lock_registration_error(
            knowledge_object,
            lock_entry,
            root,
        )
        if registration_error is not None:
            yield _blocker(
                RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
                knowledge_object.path,
                registration_error,
            )
            continue
        if not path.is_file():
            yield _blocker(
                RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
                knowledge_object.path,
                "Locked governed document is missing from the repository.",
            )
            continue
        current_sha256 = _sha256(path)
        if (
            current_sha256 != lock_entry.expected_hash
            and (
                knowledge_object.path,
                current_sha256,
            )
            not in approvals
        ):
            yield _blocker(
                RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
                knowledge_object.path,
                (
                    "Locked governed document content changed without a matching "
                    "written owner approval record for the current SHA-256."
                ),
            )


def _document_lock_registration_error(
    knowledge_object: GovernedKnowledgeObject,
    lock_entry: GovernedDocumentLockEntry,
    root: Path,
) -> str | None:
    metadata = _frontmatter(root / knowledge_object.path)
    supersedes = _frontmatter_sequence(root / knowledge_object.path, "supersedes")
    if not supersedes:
        supersedes = _frontmatter_sequence(
            root / knowledge_object.path,
            "supersedes_document_ids",
        )
    expected: dict[str, object] = {
        "canonical_path": knowledge_object.canonical_path,
        "authority_level": knowledge_object.authority_level.value,
        "authority_layer": knowledge_object.authority_layer,
        "authority_effect": (
            knowledge_object.authority_effect.value
            if knowledge_object.authority_effect is not None
            else None
        ),
        "authority_scope": knowledge_object.authority_scope,
        "document_status": knowledge_object.lifecycle_status.value,
        "version": knowledge_object.version,
        "source_of_truth": knowledge_object.source_of_truth,
        "supersedes": supersedes,
        "allowed_change_process": GOVERNED_DOCUMENT_ALLOWED_CHANGE_PROCESS,
    }
    actual: dict[str, object] = {
        "canonical_path": lock_entry.canonical_path,
        "authority_level": lock_entry.authority_level,
        "authority_layer": lock_entry.authority_layer,
        "authority_effect": lock_entry.authority_effect,
        "authority_scope": lock_entry.authority_scope,
        "document_status": lock_entry.document_status,
        "version": lock_entry.version,
        "source_of_truth": lock_entry.source_of_truth,
        "supersedes": lock_entry.supersedes,
        "allowed_change_process": lock_entry.allowed_change_process,
    }
    if metadata is None:
        return "Locked governed document metadata could not be read."
    for field, expected_value in expected.items():
        if field in {"authority_layer", "authority_effect", "authority_scope"}:
            if actual[field] is None:
                continue
        if actual[field] != expected_value:
            return f"Governed document lock manifest registration mismatch for {field}."
    return None


def _requires_governed_document_lock(
    knowledge_object: GovernedKnowledgeObject,
) -> bool:
    return (
        knowledge_object.lifecycle_status is KnowledgeLifecycleStatus.ACTIVE
        and (
            knowledge_object.source_of_truth
            or knowledge_object.machine_enforceable
            or knowledge_object.content_role is KnowledgeContentRole.POLICY_AS_CODE
        )
        and knowledge_object.classification is not KnowledgeClassification.SECRET
    )


def _document_lock_manifest(
    root: Path,
) -> tuple[
    dict[str, GovernedDocumentLockEntry],
    frozenset[tuple[str, str]],
    str | None,
]:
    path = root / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    if not path.is_file():
        return (
            {},
            frozenset(),
            (
                "Governed document lock manifest is missing; locked documents "
                "must stay protected until written owner approval exists."
            ),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, frozenset(), f"Governed document lock manifest is invalid: {exc}."
    if not isinstance(payload, dict):
        return {}, frozenset(), "Governed document lock manifest must be a JSON object."
    if payload.get("status") != "ACTIVE":
        return {}, frozenset(), "Governed document lock manifest status must be ACTIVE."
    if payload.get("written_owner_approval_required") is not True:
        return (
            {},
            frozenset(),
            ("Governed document lock manifest must require written owner approval."),
        )
    policy_error = _document_lock_manifest_policy(payload.get("manifest_lock_policy"))
    if policy_error is not None:
        return {}, frozenset(), policy_error
    entries, entry_error = _document_lock_entries(payload.get("locked_documents"))
    if entry_error is not None:
        return {}, frozenset(), entry_error
    approvals, approval_error = _document_lock_approvals(
        payload.get("approval_records", ()),
        root,
    )
    if approval_error is not None:
        return {}, frozenset(), approval_error
    written_approval_error = _document_lock_written_owner_approvals(
        payload.get("written_owner_approvals"),
        payload.get("approval_records", ()),
    )
    if written_approval_error is not None:
        return {}, frozenset(), written_approval_error
    return entries, approvals, None


def _document_lock_manifest_policy(value: object) -> str | None:
    if not isinstance(value, dict):
        return "Governed document lock manifest must declare manifest_lock_policy."
    if value.get("lock_state") != "LOCKED":
        return "Governed document lock manifest policy lock_state must be LOCKED."
    if value.get("approval_policy") != "WRITTEN_OWNER_APPROVAL_REQUIRED":
        return (
            "Governed document lock manifest policy approval_policy must be "
            "WRITTEN_OWNER_APPROVAL_REQUIRED."
        )
    if value.get("written_owner_approval_required") is not True:
        return (
            "Governed document lock manifest policy must require written owner "
            "approval."
        )
    if value.get("filesystem_lock_required") is not True:
        return (
            "Governed document lock manifest policy must require filesystem "
            "write protection."
        )
    return None


def _document_lock_entries(
    value: object,
) -> tuple[dict[str, GovernedDocumentLockEntry], str | None]:
    if not isinstance(value, list) or not value:
        return {}, "Governed document lock manifest must contain locked_documents."
    entries: dict[str, GovernedDocumentLockEntry] = {}
    for item in value:
        if not isinstance(item, dict):
            return {}, "Each governed document lock entry must be a JSON object."
        relative = item.get("path")
        sha256 = item.get("sha256")
        expected_hash = item.get("expected_hash")
        canonical_path = item.get("canonical_path")
        authority_level = item.get("authority_level")
        authority_layer = item.get("authority_layer")
        authority_effect = item.get("authority_effect")
        authority_scope = item.get("authority_scope")
        document_status = item.get("document_status")
        version = item.get("version")
        source_of_truth = item.get("source_of_truth")
        supersedes = item.get("supersedes")
        allowed_change_process = item.get("allowed_change_process")
        if not isinstance(
            relative,
            str,
        ) or not _is_safe_repository_relative_path(relative):
            return {}, "Governed document lock entry path is invalid."
        if not isinstance(
            canonical_path,
            str,
        ) or not _is_safe_repository_relative_path(canonical_path):
            return (
                {},
                f"Governed document lock canonical_path is invalid: {relative}.",
            )
        if canonical_path != relative:
            return (
                {},
                f"Governed document lock canonical_path must match path: {relative}.",
            )
        if not isinstance(authority_level, str) or not authority_level:
            return (
                {},
                f"Governed document lock authority_level is invalid: {relative}.",
            )
        if authority_layer is not None:
            if (
                not isinstance(authority_layer, str)
                or authority_layer not in _REPOSITORY_AUTHORITY_LAYERS
            ):
                return (
                    {},
                    f"Governed document lock authority_layer is invalid: {relative}.",
                )
        if authority_effect is not None:
            try:
                authority_effect = _normalize_authority_effect(authority_effect).value
            except ValueError:
                return (
                    {},
                    f"Governed document lock authority_effect is invalid: {relative}.",
                )
        if authority_scope is not None:
            if (
                not isinstance(authority_scope, str)
                or _AUTHORITY_SCOPE_RE.match(authority_scope) is None
            ):
                return (
                    {},
                    f"Governed document lock authority_scope is invalid: {relative}.",
                )
        if not isinstance(document_status, str) or not document_status:
            return (
                {},
                f"Governed document lock document_status is invalid: {relative}.",
            )
        if not isinstance(version, str) or not _SEMVER_RE.match(version):
            return {}, f"Governed document lock version is invalid: {relative}."
        if not isinstance(source_of_truth, bool):
            return (
                {},
                f"Governed document lock source_of_truth is invalid: {relative}.",
            )
        if not isinstance(supersedes, list) or any(
            not isinstance(item, str) or not item.strip() for item in supersedes
        ):
            return {}, f"Governed document lock supersedes is invalid: {relative}."
        if allowed_change_process != GOVERNED_DOCUMENT_ALLOWED_CHANGE_PROCESS:
            return (
                {},
                "Governed document lock allowed_change_process is invalid: "
                f"{relative}.",
            )
        if not isinstance(sha256, str) or _SHA256_RE.match(sha256) is None:
            return {}, f"Governed document lock entry has invalid sha256: {relative}."
        if expected_hash != sha256:
            return (
                {},
                f"Governed document lock expected_hash must match sha256: {relative}.",
            )
        if item.get("lock_state") != "LOCKED":
            return {}, f"Governed document lock_state must be LOCKED: {relative}."
        if item.get("approval_policy") != "WRITTEN_OWNER_APPROVAL_REQUIRED":
            return (
                {},
                f"Governed document approval policy is invalid: {relative}.",
            )
        if relative in entries:
            return {}, f"Governed document lock entry is duplicated: {relative}."
        entries[relative] = GovernedDocumentLockEntry(
            path=relative,
            canonical_path=canonical_path,
            authority_level=authority_level,
            authority_layer=authority_layer,
            authority_effect=authority_effect,
            authority_scope=authority_scope,
            document_status=document_status,
            version=version,
            expected_hash=expected_hash,
            source_of_truth=source_of_truth,
            supersedes=tuple(supersedes),
            allowed_change_process=allowed_change_process,
        )
    return entries, None


def _document_lock_approvals(
    value: object,
    repository_root: Path | None = None,
) -> tuple[frozenset[tuple[str, str]], str | None]:
    if not isinstance(value, list):
        return frozenset(), "approval_records must be a JSON array."
    approvals: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            return frozenset(), "Each approval record must be a JSON object."
        if item.get("approval_status") != "APPROVED":
            continue
        if item.get("written_owner_approval") is not True:
            return (
                frozenset(),
                "Approved document lock records require written approval.",
            )
        approved_hashes = item.get("approved_sha256")
        if not isinstance(approved_hashes, dict) or not approved_hashes:
            return (
                frozenset(),
                "Approved document lock record must include approved_sha256.",
            )
        evidence_error = _document_lock_approval_evidence(item, repository_root)
        if evidence_error is not None:
            return frozenset(), evidence_error
        for relative, sha256 in approved_hashes.items():
            if not isinstance(
                relative,
                str,
            ) or not _is_safe_repository_relative_path(relative):
                return frozenset(), "Approved document lock path is invalid."
            if not isinstance(sha256, str) or _SHA256_RE.match(sha256) is None:
                return (
                    frozenset(),
                    f"Approved document lock sha256 is invalid: {relative}.",
                )
            approvals.add((relative, sha256))
    return frozenset(approvals), None


def _document_lock_written_owner_approvals(
    value: object,
    approval_records: object,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return "written_owner_approvals must be a JSON array when present."
    if not isinstance(approval_records, list):
        return "approval_records must be a JSON array."
    approval_index: dict[str, dict[str, object]] = {}
    for item in approval_records:
        if not isinstance(item, dict):
            return "Each approval record must be a JSON object."
        approval_id = str(item.get("approval_id", "")).strip()
        if not approval_id:
            return "Approved document lock record approval_id is invalid."
        approval_index[approval_id] = item
    mirror_fields = (
        "approval_scope",
        "approval_status",
        "approved_by",
        "approved_at_utc",
        "written_owner_approval",
        "approved_sha256",
        "approval_evidence_path",
        "approval_evidence_sha256",
    )
    for item in value:
        if not isinstance(item, dict):
            return "Each written owner approval must be a JSON object."
        approval_id = str(item.get("approval_id", "")).strip()
        if not approval_id:
            return "Written owner approval approval_id is invalid."
        canonical_record = approval_index.get(approval_id)
        if canonical_record is None:
            return (
                "Written owner approval must be mirrored in approval_records: "
                f"{approval_id}."
            )
        for field in mirror_fields:
            if item.get(field) != canonical_record.get(field):
                return (
                    "Written owner approval mirror mismatch for "
                    f"{approval_id}: {field}."
                )
    return None


def _document_lock_approval_evidence(
    item: dict[str, object],
    repository_root: Path | None,
) -> str | None:
    evidence_path = item.get("approval_evidence_path")
    evidence_sha256 = item.get("approval_evidence_sha256")
    if evidence_path is None and evidence_sha256 is None:
        return None
    if repository_root is None:
        return "Approved document lock evidence requires repository root."
    if not isinstance(evidence_path, str) or not _is_safe_repository_relative_path(
        evidence_path
    ):
        return "Approved document lock evidence path is invalid."
    if not isinstance(evidence_sha256, str) or (
        _SHA256_RE.match(evidence_sha256) is None
    ):
        return "Approved document lock evidence sha256 is invalid."
    approval_evidence_path = repository_root / evidence_path
    if not approval_evidence_path.is_file():
        return f"Approved document lock evidence file is missing: {evidence_path}."
    if _sha256(approval_evidence_path) != evidence_sha256.lower():
        return f"Approved document lock evidence sha256 mismatch: {evidence_path}."
    try:
        payload = json.loads(approval_evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Approved document lock evidence is invalid: {exc}."
    if not isinstance(payload, dict):
        return "Approved document lock evidence must be a JSON object."
    if (
        payload.get("artifact_origin")
        != "governed_document_lock_written_owner_approval"
    ):
        return "Approved document lock evidence artifact_origin is invalid."
    expected_pairs = (
        ("approval_id", item.get("approval_id")),
        ("approval_scope", item.get("approval_scope")),
        ("approval_status", item.get("approval_status")),
        ("approved_by", item.get("approved_by")),
        ("approved_at_utc", item.get("approved_at_utc")),
    )
    for key, expected in expected_pairs:
        if payload.get(key) != expected:
            return f"Approved document lock evidence {key} does not match manifest."
    if payload.get("written_owner_approval") is not True:
        return "Approved document lock evidence must confirm written owner approval."
    if payload.get("verification_status") != "VERIFIED":
        return "Approved document lock evidence must be VERIFIED."
    if payload.get("approved_sha256") != item.get("approved_sha256"):
        return (
            "Approved document lock evidence approved_sha256 does not match manifest."
        )
    return None


def _is_safe_repository_relative_path(value: str) -> bool:
    path = Path(value)
    return (
        bool(value.strip())
        and "\\" not in value
        and not value.startswith("/")
        and not path.is_absolute()
        and ".." not in path.parts
    )


def _required_knowledge_fields() -> tuple[str, ...]:
    return (
        "document_id",
        "title",
        "document_type",
        "version",
        "status",
        "owner",
        "authority_level",
        "content_role",
        "source_of_truth",
        "canonical_path",
        "machine_enforceable",
        "audit_required",
        "classification",
    )


def _required_explicit_authority_fields(
    relative: str,
    metadata: dict[str, str],
) -> tuple[str, ...]:
    required_fields = ["authority_layer", "authority_scope"]
    if _requires_explicit_operational_authority_metadata(relative, metadata):
        required_fields.append("authority_effect")
    if (
        metadata.get("authority_layer", "").strip()
        == "L0_EXTERNAL_MANDATORY_CONSTRAINTS"
    ):
        required_fields.extend(
            (
                "external_constraint_id",
                "source_uri",
                "jurisdiction_or_provider",
                "effective_version",
                "effective_date",
                "retrieved_at",
                "content_hash",
                "validation_status",
                "affected_objects",
            )
        )
    return tuple(
        field for field in required_fields if not metadata.get(field, "").strip()
    )


def _required_knowledge_field_missing(
    field: str,
    metadata: dict[str, str],
) -> bool:
    if field == "status":
        return not (
            metadata.get("status", "").strip()
            or metadata.get("lifecycle_status", "").strip()
        )
    return not metadata.get(field, "").strip()


def _knowledge_required_section_findings(
    root: Path,
    policy: RepositoryPolicy,
) -> Iterable[RepositoryValidationFinding]:
    for relative, sections in policy.knowledge_section_requirements.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for section in sections:
            if not _has_markdown_heading(text, section):
                yield _blocker(
                    RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING,
                    relative,
                    f"Required section missing from governed standard: {section}.",
                )


def _english_only_knowledge_findings(
    root: Path,
    policy: RepositoryPolicy,
) -> Iterable[RepositoryValidationFinding]:
    for relative in _english_governed_paths(root, policy):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        offenders = _non_english_markers(text)
        if offenders:
            yield _blocker(
                RepositoryFindingKind.KNOWLEDGE_LANGUAGE_VIOLATION,
                relative,
                (
                    "Governed documentation standard must use English prose; "
                    f"detected non-English markers: {', '.join(offenders[:8])}."
                ),
            )


def _non_code_content_language_findings(
    root: Path,
    policy: RepositoryPolicy,
    artifacts: tuple[RepositoryArtifact, ...],
) -> Iterable[RepositoryValidationFinding]:
    excluded_types = {
        RepositoryArtifactType.SOURCE_CODE,
        RepositoryArtifactType.TEST,
        RepositoryArtifactType.DATA,
        RepositoryArtifactType.MODEL,
        RepositoryArtifactType.REPORT,
        RepositoryArtifactType.LOG,
        RepositoryArtifactType.STATE,
        RepositoryArtifactType.RUNTIME,
        RepositoryArtifactType.CACHE,
        RepositoryArtifactType.EVIDENCE,
        RepositoryArtifactType.ARCHIVE,
        RepositoryArtifactType.ARTIFACT,
    }
    english_only_paths = _english_governed_paths(root, policy)
    for artifact in artifacts:
        if artifact.canonical_path in english_only_paths:
            continue
        if artifact.artifact_type in excluded_types:
            continue
        path = root / artifact.canonical_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            yield _blocker(
                RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION,
                artifact.canonical_path,
                "Non-code repository content must be UTF-8 English text.",
            )
            continue
        offenders = _non_english_markers(text)
        if offenders:
            yield _blocker(
                RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION,
                artifact.canonical_path,
                (
                    "Non-code repository file content must be written in "
                    "professional English; detected non-English markers: "
                    f"{', '.join(offenders[:8])}."
                ),
            )


def _non_english_markers(text: str) -> tuple[str, ...]:
    text = _language_scan_text(text)
    for literal in _NON_ENGLISH_ALLOWED_LITERALS:
        text = text.replace(literal, "")
    turkish_chars = (
        "\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc"
    )
    turkish_character_markers = tuple(
        dict.fromkeys(re.findall(f"[{turkish_chars}]", text))
    )
    turkish_word_markers = tuple(
        dict.fromkeys(
            match.group(0)
            for match in re.finditer(
                (
                    "\\b("
                    "ajan|ajanlar|alan|amac[\u0131i]|amac\u0131|anayasasi|"
                    "arastirma|arti|balina|belge|belgeler|bilgi|bu|"
                    "beklenen|bellek|bulgu|"
                    "calismalari|calistirir|degistirmez|deneme|durum|"
                    "dosya|dokuman|dok[u\u00fc]man|dongu|edilir|eksi|"
                    "etki|"
                    "eklenemez|eksik|etkilenen|faz|formatinda|gecici|"
                    "ge[\u00e7c]erli|gelistirebilecek|gerekirse|gizli|"
                    "g[o\u00f6]sterir|guvenli|g[u\u00fc]venlik|hatalari|"
                    "icinde|icindekiler|icin|ile|insan|kan[\u0131i]t|kanit|"
                    "karantinaya|kayitlari|kaynak|kendi|kendisinden|"
                    "kimlikleri|kodlar|komut|kontrollu|konu|kriteri|"
                    "kural|kurulum|kurumsal|kisaltmalar|"
                    "mevcut|mimari|misyon|olmadan|olarak|onay|onemli|"
                    "otorite|ozet|"
                    "parcanin|raporlar|revize|sayilmaz|sinirinda|"
                    "sistem|standart|strateji|sudur|tan[\u0131i]m|temel|"
                    "tehlikeli|uygular|uyum|uyumluluk|validasyon|veri|"
                    "verin|ve|veya|vizyon|yasaktir|"
                    "yaptigini|yeni|yetki|yolu|y[o\u00f6]neti[\u015fs]im|"
                    "zorunlu"
                    ")\\b"
                ),
                text,
                flags=re.IGNORECASE,
            )
        )
    )
    return turkish_character_markers + turkish_word_markers


def _language_scan_text(text: str) -> str:
    without_fenced_code = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    without_inline_code = re.sub(r"`[^`\n]+`", " ", without_fenced_code)
    without_urls = re.sub(r"https?://\S+", " ", without_inline_code)
    return without_urls


def _has_markdown_heading(text: str, title: str) -> bool:
    pattern = re.compile(
        rf"^#+\s+(?:\d+(?:\.\d+)*\.\s+)?{re.escape(title)}\s*$",
        re.MULTILINE,
    )
    return pattern.search(text) is not None


def _knowledge_object(
    relative: str,
    metadata: dict[str, str],
) -> GovernedKnowledgeObject:
    authority_level = KnowledgeAuthorityLevel(metadata["authority_level"])
    authority_layer = metadata["authority_layer"].strip()
    authority_effect_value = metadata.get("authority_effect", "").strip()
    authority_effect = (
        _normalize_authority_effect(authority_effect_value)
        if authority_effect_value
        else None
    )
    authority_scope = metadata["authority_scope"].strip()
    return GovernedKnowledgeObject(
        knowledge_id=metadata["document_id"],
        knowledge_type=KnowledgeObjectType(metadata["document_type"]),
        title=metadata["title"],
        version=metadata["version"],
        lifecycle_status=KnowledgeLifecycleStatus(
            _knowledge_lifecycle_status(metadata)
        ),
        authority_level=authority_level,
        authority_layer=authority_layer,
        authority_effect=authority_effect,
        content_role=KnowledgeContentRole(metadata["content_role"]),
        owner=metadata["owner"],
        source_of_truth=_metadata_bool("source_of_truth", metadata),
        authority_scope=authority_scope,
        source_of_truth_scope=metadata.get("source_of_truth_scope"),
        machine_enforceable=_metadata_bool("machine_enforceable", metadata),
        audit_required=_metadata_bool("audit_required", metadata),
        classification=KnowledgeClassification(metadata["classification"]),
        path=relative,
        canonical_path=metadata["canonical_path"],
    )


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _read_utf8_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _frontmatter(path: Path) -> dict[str, str] | None:
    text = _read_utf8_text_or_none(path)
    if text is None:
        return None
    if text.startswith("---\r\n"):
        offset = 5
    elif text.startswith("---\n"):
        offset = 4
    else:
        return None
    end = text.find("\n---", offset)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for raw_line in text[offset:end].splitlines():
        if raw_line[:1].isspace():
            continue
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = _clean_metadata_value(value)
    return fields


def _frontmatter_sequence(path: Path, field: str) -> tuple[str, ...]:
    text = _read_utf8_text_or_none(path)
    if text is None:
        return ()
    if text.startswith("---\r\n"):
        offset = 5
    elif text.startswith("---\n"):
        offset = 4
    else:
        return ()
    end = text.find("\n---", offset)
    if end == -1:
        return ()
    values: list[str] = []
    in_field = False
    for raw_line in text[offset:end].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line[:1].isspace():
            key, separator, value = raw_line.partition(":")
            in_field = separator == ":" and key.strip() == field
            if in_field and value.strip():
                values.append(_clean_metadata_value(value))
            continue
        if in_field:
            item = raw_line.strip()
            if item.startswith("- "):
                values.append(_clean_metadata_value(item[2:]))
    return tuple(values)


def _clean_metadata_value(value: str) -> str:
    cleaned = value.strip().strip("\"'`")
    return cleaned


def _metadata_bool(field: str, metadata: dict[str, str]) -> bool:
    value = metadata[field].strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def _governed_knowledge_count(root: Path, policy: RepositoryPolicy) -> int:
    count = 0
    for relative in dict.fromkeys(
        (
            *policy.knowledge_metadata_required_paths,
            *_governed_markdown_knowledge_paths(root),
        )
    ):
        path = root / relative
        if path.is_file() and _frontmatter(path) is not None:
            count += 1
    return count


def _allowed_artifact_results() -> tuple[str, ...]:
    return (
        "COMPLIANT",
        "WARNING",
        "BLOCKER",
        "MOVE_RECOMMENDED",
        "ARCHIVE_RECOMMENDED",
        "QUARANTINE_REQUIRED",
        "NO_CHANGE",
    )


def _result_counts(artifacts: tuple[RepositoryArtifact, ...]) -> dict[str, int]:
    counts = dict.fromkeys(_allowed_artifact_results(), 0)
    for artifact in artifacts:
        counts[artifact.result] = counts.get(artifact.result, 0) + 1
    return counts


def _migration_map_payload(
    artifacts: tuple[RepositoryArtifact, ...],
    actions: tuple[RepositoryRemediationAction, ...],
) -> tuple[dict[str, object], ...]:
    planned_entries = [
        {
            "source_path": artifact.canonical_path,
            "target_path": artifact.proposed_path,
            "reason": _migration_reason(artifact),
            "authority_level": _artifact_authority_level(artifact),
            "status": artifact.action,
            "requires_link_update": True,
            "requires_reference_update": True,
            "risk": _migration_risk(artifact),
        }
        for artifact in artifacts
        if artifact.action in {"MOVE_RECOMMENDED", "ARCHIVE_RECOMMENDED"}
        and artifact.proposed_path is not None
    ]
    action_entries = [
        {
            "source_path": action.current_path,
            "target_path": action.proposed_path,
            "reason": action.reason,
            "authority_level": "REPOSITORY",
            "status": action.action_type,
            "requires_link_update": action.proposed_path is not None,
            "requires_reference_update": action.proposed_path is not None,
            "risk": "REVIEW_REQUIRED",
        }
        for action in actions
        if action.proposed_path is not None
    ]
    merged: dict[str, dict[str, object]] = {}
    for entry in (*planned_entries, *action_entries):
        merged[str(entry["source_path"])] = entry
    return tuple(merged[path] for path in sorted(merged))


def _dashboard_metrics(report: RepositoryValidationReport) -> dict[str, int]:
    artifacts = report.artifacts
    finding_kinds = [finding.kind for finding in report.findings]
    metrics = {
        "root_clutter_count": sum(
            1
            for artifact in artifacts
            if "/" not in artifact.canonical_path
            and artifact.artifact_class
            in {
                RepositoryArtifactClass.CACHE,
                RepositoryArtifactClass.REPORT,
                RepositoryArtifactClass.RUNTIME,
                RepositoryArtifactClass.ARCHIVE,
            }
        ),
        "duplicate_source_of_truth_count": finding_kinds.count(
            RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT
        ),
        "unclassified_artifact_count": sum(
            1
            for artifact in artifacts
            if artifact.artifact_type is RepositoryArtifactType.ARTIFACT
            and artifact.action == "NO_CHANGE"
        ),
        "cache_runtime_leakage_count": sum(
            1
            for artifact in artifacts
            if artifact.artifact_type
            in {RepositoryArtifactType.CACHE, RepositoryArtifactType.RUNTIME}
        ),
        "stale_document_count": sum(
            1
            for artifact in artifacts
            if artifact.lifecycle_status.name == "DEPRECATED"
        ),
        "missing_metadata_count": finding_kinds.count(
            RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
        ),
        "broken_canonical_path_count": finding_kinds.count(
            RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        ),
        "policy_schema_mismatch_count": finding_kinds.count(
            RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING
        ),
        "unresolved_governance_blocker_count": len(report.blockers),
        "authority_graph_conflict_count": finding_kinds.count(
            RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT
        )
        + finding_kinds.count(RepositoryFindingKind.AUTHORITY_GRAPH_INVALID),
    }
    for artifact_class in RepositoryArtifactClass:
        metrics[f"{artifact_class.value.lower()}_artifact_count"] = sum(
            1 for artifact in artifacts if artifact.artifact_class is artifact_class
        )
    return metrics


def _root_inventory_payload(
    artifacts: tuple[RepositoryArtifact, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "file_id": artifact.file_id,
            "path": artifact.path,
            "mime_type": artifact.mime_type,
            "size": artifact.size,
            "modified_time": artifact.modified_time,
            "owner": artifact.owner,
            "shared_status": artifact.shared_status,
            "artifact_type": artifact.artifact_type.value,
            "artifact_class": artifact.artifact_class.value,
            "authority_layer": artifact.authority_layer,
            "authority_effect": (
                artifact.authority_effect.value
                if artifact.authority_effect is not None
                else None
            ),
            "authority_scope": artifact.authority_scope,
            "observed_expected_layer": artifact.observed_expected_layer,
            "authority_basis": artifact.authority_basis,
            "action": artifact.action,
            "result": artifact.result,
        }
        for artifact in artifacts
        if "/" not in artifact.canonical_path
    )


def _write_report_json(path: Path, report: RepositoryValidationReport) -> None:
    _ensure_output_path(path)
    path.write_text(
        json.dumps(report.to_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_findings_json(path: Path, report: RepositoryValidationReport) -> None:
    _ensure_output_path(path)
    payload = {
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_source_path": report.policy_source_path,
        "generated_at_utc": report.analyzed_at_utc,
        "status": report.status,
        "finding_count": len(report.findings),
        "blocker_count": len(report.blockers),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "findings": tuple(to_primitive(finding) for finding in report.findings),
        "blockers": report.blockers,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_policy_snapshot_json(
    path: Path,
    report: RepositoryValidationReport,
    policy: RepositoryPolicy,
) -> None:
    _ensure_output_path(path)
    payload = {
        "snapshot_type": "REPOSITORY_VALIDATOR_POLICY_SNAPSHOT",
        "generated_at_utc": report.analyzed_at_utc,
        "policy_source_path": report.policy_source_path,
        "policy": asdict(policy),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_mirror_report_json(path: Path, report: MirrorHygieneReport) -> None:
    _ensure_output_path(path)
    path.write_text(
        json.dumps(report.to_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_mirror_cleanup_plan(path: Path, report: MirrorHygieneReport) -> None:
    _ensure_output_path(path)
    payload = {
        "policy_id": report.policy_id,
        "mirror_manifest_path": report.mirror_manifest_path,
        "generated_at_utc": report.analyzed_at_utc,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "cleanup_plan": tuple(to_primitive(entry) for entry in report.cleanup_plan),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _mirror_manifest_payload(
    report: RepositoryValidationReport,
    *,
    policy: RepositoryMirrorPolicy,
) -> dict[str, object]:
    entries = []
    for artifact in sorted(report.artifacts, key=lambda item: item.path):
        classification = _mirror_path_classification(artifact.path, policy)
        if _mirror_path_finding(artifact.path, classification) is not None:
            continue
        entries.append(
            {
                "path": artifact.path,
                "git_tracked": artifact.git_tracked,
                "source_of_truth": False,
                "authority": policy.mirror_authority,
            }
        )
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
        "mirror_role": policy.mirror_role,
        "authority": policy.mirror_authority,
        "source_of_truth": False,
        "generated_at_utc": report.analyzed_at_utc,
        "repository_root": report.repository_root,
        "root_inventory": entries,
        "entry_count": len(entries),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _write_mirror_manifest_json(
    path: Path,
    report: RepositoryValidationReport,
    *,
    policy: RepositoryMirrorPolicy,
) -> None:
    _ensure_output_path(path)
    path.write_text(
        json.dumps(
            _mirror_manifest_payload(report, policy=policy),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_mirror_report_markdown(path: Path, report: MirrorHygieneReport) -> None:
    _ensure_output_path(path)
    lines = [
        "---",
        "document_id: AI4B-GOV-EVID-MIRROR-HYGIENE-001",
        "title: AI4BINANCE Repository Mirror Hygiene Findings",
        "document_type: EVIDENCE_REQUIREMENT",
        "version: 1.0.0",
        "status: ACTIVE",
        "owner: Enterprise Engineering Governance",
        "authority_level: ADVISORY",
        "content_role: GENERATED",
        "source_of_truth: false",
        "machine_enforceable: false",
        "audit_required: true",
        "classification: INTERNAL",
        f"created_at_utc: {report.analyzed_at_utc}",
        "---",
        "",
        "# AI4BINANCE Repository Mirror Hygiene Validation",
        "",
        "## ELI10",
        "",
        (
            "This report checks a non-authoritative mirror inventory. It does not "
            "delete files, approve trading, or make the mirror canonical."
        ),
        "",
        "## Summary",
        "",
        f"- status: `{report.status}`",
        f"- policy: `{report.policy_id}@{report.policy_version}`",
        f"- mirror_role: `{report.mirror_role}`",
        f"- mirror_authority: `{report.mirror_authority}`",
        f"- entry_count: `{report.entry_count}`",
        f"- finding_count: `{len(report.findings)}`",
        f"- blocker_count: `{len(report.blockers)}`",
        f"- execution_allowed: `{report.execution_allowed}`",
        f"- promotion_status: `{report.promotion_status}`",
        f"- live_eligibility_status: `{report.live_eligibility_status}`",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("- No mirror hygiene findings.")
    else:
        for finding in report.findings:
            lines.append(
                "- "
                f"`{finding.severity}` "
                f"`{finding.kind}` "
                f"`{_markdown_table_cell(finding.path)}` - "
                f"{_markdown_table_cell(finding.detail)}"
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_report_markdown(path: Path, report: RepositoryValidationReport) -> None:
    _ensure_output_path(path)
    lines = [
        "---",
        "document_id: AI4B-GOV-EVID-REPO-FINDINGS-001",
        "title: AI4BINANCE Repository Governance Findings",
        "document_type: EVIDENCE_REQUIREMENT",
        "version: 1.0.0",
        "status: ACTIVE",
        "owner: Enterprise Engineering Governance",
        "authority_level: ADVISORY",
        "content_role: GENERATED",
        "source_of_truth: false",
        "machine_enforceable: false",
        "audit_required: true",
        "classification: INTERNAL",
        (
            "canonical_path: "
            "docs/reports/governance/report_repository_governance_findings.md"
        ),
        f"created_at_utc: {report.analyzed_at_utc}",
        "---",
        "",
        "# AI4BINANCE Repository Governance Validation",
        "",
        "## ELI10",
        "",
        (
            "This report checks whether repository files follow the governed "
            "knowledge and file-structure rules. It is report-only: it lists "
            "blockers but does not change files, approve trading or widen "
            "authority."
        ),
        "",
        "## Summary",
        "",
        f"- status: `{report.status}`",
        f"- policy: `{report.policy_id}@{report.policy_version}`",
        f"- artifact_count: `{report.artifact_count}`",
        f"- governed_knowledge_count: `{report.governed_knowledge_count}`",
        f"- finding_count: `{len(report.findings)}`",
        f"- blocker_count: `{len(report.blockers)}`",
        f"- repository_health_score: `{report.repository_health_score}`",
        f"- execution_allowed: `{report.execution_allowed}`",
        f"- promotion_status: `{report.promotion_status}`",
        f"- live_eligibility_status: `{report.live_eligibility_status}`",
        "",
        "## Findings",
        "",
    ]
    if report.findings:
        lines.extend(
            (
                f"- `{finding.severity}` `{finding.kind}` `{finding.path}`: "
                f"{finding.detail}"
            )
            for finding in report.findings
        )
    else:
        lines.append("- No findings.")
    lines.extend(("", "## Recommended Actions", ""))
    if report.recommended_actions:
        lines.extend(
            (
                f"- `{action.action_type}` `{action.current_path}`"
                f"{_markdown_proposed_path(action.proposed_path)}: "
                f"{action.reason} "
                f"(requires_approval=`{action.requires_approval}`, "
                f"destructive=`{action.destructive}`)"
            )
            for action in report.recommended_actions
        )
    else:
        lines.append("- No recommended actions.")
    lines.extend(("", "## Dashboard Metrics", ""))
    for key, value in _dashboard_metrics(report).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        (
            "",
            "## Safety",
            "",
            "- Repository validation is deterministic and report-only.",
            (
                "- It does not rewrite files, approve waivers, alter risk, "
                "or place orders."
            ),
            "- Live eligibility remains `LIVE_ORDER_BLOCKED`.",
            "",
        )
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_migration_map_markdown(
    path: Path, report: RepositoryValidationReport
) -> None:
    _ensure_output_path(path)
    migration_map = cast(
        tuple[dict[str, object], ...],
        report.to_payload()["migration_map"],
    )
    lines = [
        "---",
        "document_id: AI4B-GOV-EVID-MIGRATION-MAP-001",
        "title: AI4BINANCE Repository Governance Migration Map",
        "document_type: EVIDENCE_REQUIREMENT",
        "version: 1.0.0",
        "status: ACTIVE",
        "owner: Enterprise Engineering Governance",
        "authority_level: ADVISORY",
        "content_role: GENERATED",
        "source_of_truth: false",
        "machine_enforceable: false",
        "audit_required: true",
        "classification: INTERNAL",
        "canonical_path: docs/reports/governance/report_governance_migration_map.md",
        f"created_at_utc: {report.analyzed_at_utc}",
        "---",
        "",
        "# AI4BINANCE Repository Governance Migration Map",
        "",
        "## ELI10",
        "",
        (
            "This generated map lists proposed file moves before any rename or "
            "migration is performed. It is report-only and requires review "
            "before filesystem changes."
        ),
        "",
        (
            "| source_path | target_path | reason | authority_level | status | "
            "requires_link_update | requires_reference_update | risk |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if migration_map:
        for entry in migration_map:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(str(entry[field]))
                    for field in (
                        "source_path",
                        "target_path",
                        "reason",
                        "authority_level",
                        "status",
                        "requires_link_update",
                        "requires_reference_update",
                        "risk",
                    )
                )
                + " |"
            )
    else:
        lines.append(
            "| NO_CHANGE | NO_CHANGE | No migration is currently recommended. | "
            "ADVISORY | NO_CHANGE | false | false | LOW |"
        )
    lines.extend(
        (
            "",
            "## Safety",
            "",
            (
                "- This file does not authorize moves, deletes, renames, "
                "or live execution."
            ),
            "- Live eligibility remains `LIVE_ORDER_BLOCKED`.",
            "",
        )
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _markdown_proposed_path(proposed_path: str | None) -> str:
    if proposed_path is None:
        return ""
    return f" -> `{proposed_path}`"


def _recommended_actions(
    findings: tuple[RepositoryValidationFinding, ...],
) -> Iterable[RepositoryRemediationAction]:
    for finding in findings:
        proposed_path = _proposed_remediation_path(finding)
        yield RepositoryRemediationAction(
            action_id=str(
                uuid5(
                    NAMESPACE_URL,
                    "ai4binance:repository-remediation:"
                    f"{finding.kind.value}:{finding.path}",
                )
            ),
            finding_kind=finding.kind,
            action_type=_remediation_action_type(finding.kind),
            current_path=finding.path,
            proposed_path=proposed_path,
            reason=finding.detail,
            destructive=finding.kind
            in {
                RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC,
                RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC,
            },
            requires_approval=finding.blocker
            or finding.kind
            in {
                RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
                RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
            },
            evidence_required=(
                "pre_change_validation_report",
                "impact_analysis",
                "post_change_validation_report",
                "correction_journal_entry",
            ),
        )


def _remediation_action_type(kind: RepositoryFindingKind) -> str:
    mapping = {
        RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING: (
            "CREATE_TRACKED_GOVERNANCE_ARTIFACT_WHEN_NEEDED"
        ),
        RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH: "REGISTER_OR_MOVE_PATH_REVIEW",
        RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE: "MOVE_REVIEW_REQUIRED",
        RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION: "RENAME_REVIEW_REQUIRED",
        RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION: "RENAME_REVIEW_REQUIRED",
        RepositoryFindingKind.FORBIDDEN_SOURCE_FILENAME: "RENAME_REVIEW_REQUIRED",
        RepositoryFindingKind.SOURCE_VERSION_FILENAME: "RENAME_REVIEW_REQUIRED",
        RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC: "MOVE_REVIEW_REQUIRED",
        RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC: "MOVE_REVIEW_REQUIRED",
        RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH: "CONFIGURE_RELATIVE_PATH",
        RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION: (
            "RESOLVE_CANONICAL_IMPORT_BOUNDARY"
        ),
        RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY: (
            "SPLIT_OR_RELOCATE_CANONICAL_OWNERSHIP"
        ),
        RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING: "ADD_METADATA",
        RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID: "FIX_METADATA",
        RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION: (
            "FIX_GOVERNED_KNOWLEDGE_LIFECYCLE"
        ),
        RepositoryFindingKind.KNOWLEDGE_ID_DUPLICATE: "DEDUPLICATE_KNOWLEDGE_ID",
        RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT: (
            "RESOLVE_SOURCE_OF_TRUTH"
        ),
        RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT: (
            "REALIGN_AUTHORITY_SCOPE"
        ),
        RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION: (
            "RENAME_SOURCE_OF_TRUTH_FILE"
        ),
        RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING: (
            "ADD_REQUIRED_SECTION"
        ),
        RepositoryFindingKind.KNOWLEDGE_LANGUAGE_VIOLATION: (
            "REWRITE_AS_PROFESSIONAL_ENGLISH"
        ),
        RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION: (
            "REWRITE_AS_PROFESSIONAL_ENGLISH"
        ),
        RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION: (
            "RECLASSIFY_RUNTIME_MARKDOWN"
        ),
        RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION: (
            "REQUIRE_WRITTEN_OWNER_APPROVAL"
        ),
        RepositoryFindingKind.KNOWLEDGE_OUTPUT_WRITE_FAILED: "FIX_OUTPUT_PATH",
        RepositoryFindingKind.BLOCKER_REGISTRY_INVALID: "FIX_BLOCKER_REGISTRY",
        RepositoryFindingKind.AUTHORITY_GRAPH_INVALID: "FIX_AUTHORITY_GRAPH",
        RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT: "RECONCILE_AUTHORITY_GRAPH",
        RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION: (
            "FIX_TECHNOLOGY_LANGUAGE_POLICY"
        ),
        RepositoryFindingKind.TERMINOLOGY_POLICY_VIOLATION: ("FIX_TERMINOLOGY_POLICY"),
        RepositoryFindingKind.TERMINOLOGY_PROHIBITED_TERM: (
            "REPLACE_PROHIBITED_TERMINOLOGY"
        ),
        RepositoryFindingKind.TERMINOLOGY_DEPRECATED_ALIAS: (
            "REVIEW_TERMINOLOGY_MIGRATION"
        ),
        RepositoryFindingKind.GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION: (
            "REPAIR_GOVERNANCE_ENFORCEMENT_FABRIC"
        ),
    }
    return mapping[kind]


def _proposed_remediation_path(finding: RepositoryValidationFinding) -> str | None:
    if finding.kind in {
        RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION,
        RepositoryFindingKind.FORBIDDEN_SOURCE_FILENAME,
        RepositoryFindingKind.SOURCE_VERSION_FILENAME,
        RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION,
    }:
        path = Path(finding.path)
        return path.with_name(_snake_case_filename(path.name)).as_posix()
    if finding.kind is RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC:
        path = Path(finding.path)
        return (
            "runtime/artifacts/repository_validation/governance/remediation/"
            f"{path.name}"
        )
    if finding.kind is RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC:
        return f"runtime/state/governance/{Path(finding.path).name}"
    if finding.kind is RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE:
        return _LEGACY_RUNTIME_ROOT_TARGETS.get(finding.path)
    if finding.kind is RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING:
        return finding.path
    return None


def _snake_case_filename(filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()
    snake = re.sub(r"[^a-z0-9_]+", "_", snake).strip("_")
    snake = re.sub(r"_+", "_", snake)
    snake = re.sub(r"_(v\d+|final|fixed|new_final\d*)$", "", snake)
    return f"{snake or 'renamed_artifact'}{suffix.lower()}"


def _ensure_output_path(path: Path) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)


def _absolute_path_findings(
    path: Path,
    root: Path,
    policy: RepositoryPolicy,
) -> Iterable[RepositoryValidationFinding]:
    relative = _relative(path, root)
    text = path.read_text(encoding="utf-8")
    allowed_literals = {
        _normalize_path_literal(allowed)
        for allowed in policy.allowed_absolute_path_literals
    }
    for match in _ABSOLUTE_PATH_RE.finditer(text):
        literal = match.group(0)
        if _normalize_path_literal(literal) in allowed_literals:
            continue
        yield _blocker(
            RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH,
            relative,
            f"Hard-coded machine-specific absolute path detected near {literal!r}.",
        )


def _normalize_path_literal(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")


def _blocker(
    kind: RepositoryFindingKind,
    path: str,
    detail: str,
) -> RepositoryValidationFinding:
    return RepositoryValidationFinding(
        kind=kind,
        severity=RepositoryFindingSeverity.HIGH,
        path=path,
        detail=detail,
        blocker=True,
    )


def _control_family(kind: RepositoryFindingKind) -> RepositoryControlFamily:
    if kind in {
        RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
        RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
        RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION,
        RepositoryFindingKind.KNOWLEDGE_ID_DUPLICATE,
        RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT,
        RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT,
        RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION,
        RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING,
        RepositoryFindingKind.KNOWLEDGE_LANGUAGE_VIOLATION,
        RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION,
        RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION,
        RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION,
        RepositoryFindingKind.KNOWLEDGE_OUTPUT_WRITE_FAILED,
    }:
        return RepositoryControlFamily.DOC_HYGIENE
    if kind in {
        RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
        RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
        RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT,
        RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
        RepositoryFindingKind.MIRROR_FORBIDDEN_PATH,
        RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION,
        RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION,
    }:
        return RepositoryControlFamily.ARTIFACT_HYGIENE
    if kind in {
        RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE,
        RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC,
        RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC,
        RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
        RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
    }:
        return RepositoryControlFamily.RUNTIME_HYGIENE
    if kind in {RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH}:
        return RepositoryControlFamily.CONFIG_HYGIENE
    if kind in {RepositoryFindingKind.BLOCKER_REGISTRY_INVALID}:
        return RepositoryControlFamily.POLICY_HYGIENE
    if kind in {
        RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION,
        RepositoryFindingKind.TERMINOLOGY_POLICY_VIOLATION,
        RepositoryFindingKind.TERMINOLOGY_PROHIBITED_TERM,
        RepositoryFindingKind.TERMINOLOGY_DEPRECATED_ALIAS,
        RepositoryFindingKind.GOVERNANCE_ENFORCEMENT_FABRIC_VIOLATION,
    }:
        return RepositoryControlFamily.POLICY_HYGIENE
    if kind in {
        RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION,
        RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION,
        RepositoryFindingKind.FORBIDDEN_SOURCE_FILENAME,
        RepositoryFindingKind.SOURCE_VERSION_FILENAME,
        RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION,
        RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY,
    }:
        return RepositoryControlFamily.SOURCE_HYGIENE
    return RepositoryControlFamily.REPOSITORY_CONFORMANCE


def _rule_id(kind: RepositoryFindingKind) -> str:
    return f"RV-{kind.value}"


def _finding_blocker_id(finding: RepositoryValidationFinding) -> str:
    return f"{finding.kind.value}:{finding.path}"


def _deterministic_finding_id(kind: RepositoryFindingKind, path: str) -> str:
    digest = hashlib.sha256(f"{kind.value}:{path}".encode()).hexdigest()
    return f"RFG-{kind.value}-{digest[:12]}"


def _artifact_type(
    relative: str,
    policy: RepositoryPolicy,
) -> RepositoryArtifactType:
    parts = Path(relative).parts
    if relative == ".coverage" or relative.startswith(".coverage."):
        return RepositoryArtifactType.CACHE
    if _is_disposable_generated_artifact(relative):
        return RepositoryArtifactType.CACHE
    if _is_source_runtime_artifact(relative):
        return RepositoryArtifactType.RUNTIME
    if any(part in set(policy.cache_parts) for part in parts):
        return RepositoryArtifactType.CACHE
    if relative.startswith("docs/archive/"):
        return RepositoryArtifactType.ARCHIVE
    if relative.startswith(("artifacts/", "reports/")):
        return RepositoryArtifactType.EVIDENCE
    if relative.startswith(
        ("runtime/state/", "runtime/logs/", "runtime/data/", "runtime/models/")
    ):
        return RepositoryArtifactType.RUNTIME
    if _is_under(relative, policy.source_roots) or relative.startswith("scripts/"):
        return RepositoryArtifactType.SOURCE_CODE
    if _is_under(relative, policy.test_roots):
        return RepositoryArtifactType.TEST
    if relative in {
        ".env.example",
        ".gitattributes",
        ".gitignore",
        ".python-version",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
    } or relative.startswith(".vscode/"):
        return RepositoryArtifactType.CONFIG
    if relative.startswith("config/"):
        return RepositoryArtifactType.CONFIG
    if relative.startswith("schemas/"):
        return RepositoryArtifactType.SCHEMA
    if relative.startswith("policies/"):
        return RepositoryArtifactType.POLICY
    if relative.startswith("ontology/"):
        return RepositoryArtifactType.ONTOLOGY
    if relative.startswith("workflows/"):
        return RepositoryArtifactType.WORKFLOW
    if relative.startswith("migrations/"):
        return RepositoryArtifactType.MIGRATION
    if _is_under(relative, policy.docs_roots):
        return RepositoryArtifactType.GOVERNANCE
    if relative.startswith("data/"):
        return RepositoryArtifactType.DATA
    if relative.startswith("models/"):
        return RepositoryArtifactType.MODEL
    if relative.startswith((".agents/", ".codex/", ".github/", "factory/")):
        return RepositoryArtifactType.GOVERNANCE
    if relative in {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "docs/governance/instruction_core_custom_instructions.md",
    }:
        return RepositoryArtifactType.GOVERNANCE
    if relative in {
        "docs/standards/standard_engineering_python_clean_code_vscode_development.md",
        "docs/archive/reference_local_computer_profile.md",
    }:
        return RepositoryArtifactType.GOVERNANCE
    if relative.startswith("runtime/skill_staging/"):
        return RepositoryArtifactType.RUNTIME
    if relative.startswith("tools/"):
        return RepositoryArtifactType.ARTIFACT
    return RepositoryArtifactType.ARTIFACT


def _artifact_class(
    relative: str,
    artifact_type: RepositoryArtifactType,
) -> RepositoryArtifactClass:
    if artifact_type is RepositoryArtifactType.ARCHIVE:
        return RepositoryArtifactClass.ARCHIVE
    if artifact_type is RepositoryArtifactType.CACHE:
        return RepositoryArtifactClass.CACHE
    if artifact_type in {
        RepositoryArtifactType.EVIDENCE,
        RepositoryArtifactType.REPORT,
    }:
        return RepositoryArtifactClass.REPORT
    if artifact_type in {
        RepositoryArtifactType.DATA,
        RepositoryArtifactType.LOG,
        RepositoryArtifactType.MODEL,
        RepositoryArtifactType.RUNTIME,
        RepositoryArtifactType.STATE,
    }:
        return RepositoryArtifactClass.RUNTIME
    if artifact_type in {
        RepositoryArtifactType.GOVERNANCE,
        RepositoryArtifactType.ONTOLOGY,
        RepositoryArtifactType.POLICY,
        RepositoryArtifactType.SCHEMA,
        RepositoryArtifactType.WORKFLOW,
        RepositoryArtifactType.MIGRATION,
    } or relative.startswith(("docs/", ".agents/", ".codex/")):
        return RepositoryArtifactClass.GOVERNANCE
    return RepositoryArtifactClass.SOURCE


def _mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed is not None:
        return guessed
    if path.suffix in {".md", ".txt", ".yaml", ".yml", ".toml", ".ps1"}:
        return "text/plain"
    return "application/octet-stream"


def _artifact_authority_layer(authority_evidence: AuthorityEvidence) -> str | None:
    if authority_evidence.metadata is not None:
        return _metadata_authority_layer(authority_evidence.metadata)
    return None


def _observed_expected_layer(
    relative: str,
    artifact_type: RepositoryArtifactType,
) -> str:
    return _policy_placement_layer(relative, artifact_type)


def _metadata_authority_layer(metadata: GovernedKnowledgeObject) -> str:
    return metadata.authority_layer


def _is_core_constitution(metadata: GovernedKnowledgeObject) -> bool:
    normalized_title = _normalize_title(metadata.title)
    return (
        metadata.knowledge_id == "AI4B-GOV-OEK-003"
        or "constitution" in normalized_title
    )


def _policy_placement_layer(
    relative: str,
    artifact_type: RepositoryArtifactType,
) -> str:
    if relative == "docs/governance/policy_organization_constitution_handbook.md":
        return "L1_CORE_CONSTITUTION"
    if relative in {
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "docs/governance/instruction_core_custom_instructions.md",
    }:
        return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    if relative == "README.md":
        return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    if relative.startswith(("docs/governance/", "docs/compliance/")):
        return "L2_GOVERNANCE_COMPLIANCE"
    if relative.startswith(("docs/contracts/", "schemas/")):
        return "L3_CANONICAL_CONTRACTS_SCHEMAS"
    if relative.startswith(
        (
            "docs/controls/",
            "docs/policies/",
            "docs/quality/",
            "docs/security/",
            "docs/standards/",
            "policies/",
        )
    ):
        return "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES"
    if relative.startswith(
        (
            "docs/registries/",
            "docs/roadmap/",
        )
    ):
        return "L5_REGISTRIES_ROADMAP"
    if relative.startswith(
        (
            "docs/architecture/",
            "docs/adr/",
            "docs/ontology/",
            "ontology/",
        )
    ):
        return "L6_ARCHITECTURE_ONTOLOGY_ADR"
    if relative.startswith(
        (
            "docs/providers/",
            "docs/workflows/",
            "docs/procedures/",
            "docs/runbooks/",
            "workflows/",
            ".agents/",
            ".codex/",
            ".github/",
        )
    ):
        return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    if relative.startswith(
        (
            "docs/reports/",
            "docs/inventories/",
            "runtime/",
        )
    ):
        return "L8_REPORTS_EVIDENCE_INVENTORIES"
    if relative.startswith(("docs/references/", "docs/templates/")):
        return "L9_REFERENCES_TEMPLATES"
    if relative.startswith(("docs/archive/", "archive/")):
        return "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
    if relative.startswith("docs/"):
        return "L2_GOVERNANCE_COMPLIANCE"
    if artifact_type in {
        RepositoryArtifactType.SOURCE_CODE,
        RepositoryArtifactType.CONFIG,
        RepositoryArtifactType.TEST,
        RepositoryArtifactType.SCHEMA,
        RepositoryArtifactType.POLICY,
        RepositoryArtifactType.ONTOLOGY,
        RepositoryArtifactType.WORKFLOW,
        RepositoryArtifactType.MIGRATION,
    }:
        return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    if artifact_type in {
        RepositoryArtifactType.EVIDENCE,
        RepositoryArtifactType.RUNTIME,
        RepositoryArtifactType.CACHE,
        RepositoryArtifactType.REPORT,
        RepositoryArtifactType.LOG,
        RepositoryArtifactType.STATE,
    }:
        return "L8_REPORTS_EVIDENCE_INVENTORIES"
    if artifact_type is RepositoryArtifactType.ARCHIVE:
        return "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
    return "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"


def _authority_basis(
    authority_evidence: AuthorityEvidence,
    *,
    observed_expected_layer: str,
) -> tuple[str, ...]:
    metadata = authority_evidence.metadata
    if metadata is None:
        metadata_basis = "metadata:missing"
        validation_basis = AUTHORITY_BASIS_METADATA_MISSING
    else:
        authority_effect = (
            metadata.authority_effect.value
            if metadata.authority_effect is not None
            else "none"
        )
        metadata_basis = (
            "metadata:"
            f"authority_layer={metadata.authority_layer};"
            f"authority_effect={authority_effect};"
            f"authority_scope={metadata.authority_scope};"
            f"authority_level_legacy={metadata.authority_level.value};"
            f"document_type={metadata.knowledge_type.value};"
            f"content_role={metadata.content_role.value};"
            f"source_of_truth={str(metadata.source_of_truth).lower()}"
        )
        validation_basis = AUTHORITY_BASIS_GOVERNED_METADATA_VALIDATED
    policy_basis = (
        "registered_policy:knowledge_metadata_required"
        if authority_evidence.registered_policy
        else "registered_policy:repository_policy"
    )
    canonical_basis = (
        "canonical_path:verified"
        if authority_evidence.canonical_path_verified
        else "canonical_path:invalid"
    )
    usage_basis = f"downstream_usage:{authority_evidence.downstream_usage_count}"
    return (
        metadata_basis,
        policy_basis,
        canonical_basis,
        validation_basis,
        AUTHORITY_BASIS_PLACEMENT_HINT_ONLY,
        f"{PLACEMENT_HINT_PREFIX}{observed_expected_layer}",
        usage_basis,
    )


def _proposed_artifact_path(relative: str, policy: RepositoryPolicy) -> str | None:
    if relative in policy.legacy_path_targets:
        return policy.legacy_path_targets[relative]
    return None


def _artifact_action(
    relative: str,
    artifact_type: RepositoryArtifactType,
    proposed_path: str | None,
) -> str:
    if proposed_path is not None:
        if relative == "docs/archive/reference_local_computer_profile.md":
            return "ARCHIVE_RECOMMENDED"
        return "MOVE_RECOMMENDED"
    if artifact_type is RepositoryArtifactType.CACHE:
        return "ARCHIVE_RECOMMENDED"
    return "NO_CHANGE"


def _artifact_result(action: str) -> str:
    if action == "NO_CHANGE":
        return "COMPLIANT"
    return action


def _migration_reason(artifact: RepositoryArtifact) -> str:
    if artifact.action == "ARCHIVE_RECOMMENDED":
        return "separate_local_or_historical_context_from_governed_source"
    return "normalize_governed_document_path_to_document_type_domain_subject"


def _artifact_authority_level(artifact: RepositoryArtifact) -> str:
    metadata_prefix = "metadata:authority_level="
    legacy_prefix = "authority_level_legacy="
    for basis in artifact.authority_basis:
        if not basis.startswith(metadata_prefix):
            parts = basis.split(";")
            for part in parts:
                if part.startswith(legacy_prefix):
                    return part.removeprefix(legacy_prefix)
            continue
        return basis.removeprefix(metadata_prefix).split(";", 1)[0]
    if artifact.artifact_type in {
        RepositoryArtifactType.GOVERNANCE,
        RepositoryArtifactType.POLICY,
        RepositoryArtifactType.SCHEMA,
        RepositoryArtifactType.WORKFLOW,
        RepositoryArtifactType.MIGRATION,
    }:
        return "NORMATIVE"
    return "REPOSITORY"


def _migration_risk(artifact: RepositoryArtifact) -> str:
    if artifact.action == "ARCHIVE_RECOMMENDED":
        return "LOW_WITH_REVIEW"
    return "REFERENCE_UPDATE_REQUIRED"


def _owner(relative: str, policy: RepositoryPolicy) -> str:
    top_level = relative.split("/", 1)[0]
    return policy.owner_by_top_level.get(top_level, "RepositoryGovernance")


def _registered_top_level_paths(policy: RepositoryPolicy) -> set[str]:
    return {
        *policy.allowed_top_level_paths,
        *policy.owner_by_top_level,
        *(relative.split("/", 1)[0] for relative in policy.source_roots),
        *(relative.split("/", 1)[0] for relative in policy.test_roots),
        *(relative.split("/", 1)[0] for relative in policy.docs_roots),
        *(relative.split("/", 1)[0] for relative in policy.generated_roots),
    }


def _english_governed_paths(root: Path, policy: RepositoryPolicy) -> set[str]:
    return set(
        dict.fromkeys(
            (
                *policy.english_only_knowledge_paths,
                *_governed_markdown_knowledge_paths(root),
            )
        )
    )


def _domain(relative: str) -> str:
    parts = relative.split("/")
    if len(parts) >= 3 and parts[0] == "src" and parts[1] == "ai4binance":
        return parts[2]
    return parts[0]


def _is_immutable(relative: str, artifact_type: RepositoryArtifactType) -> bool:
    return artifact_type in {
        RepositoryArtifactType.DATA,
        RepositoryArtifactType.LOG,
        RepositoryArtifactType.REPORT,
    } or relative.startswith("artifacts/")


def _is_sensitive(relative: str, policy: RepositoryPolicy) -> bool:
    return _is_under(relative, policy.protected_roots) or relative == ".env"


def _is_under(relative: str, roots: tuple[str, ...]) -> bool:
    return any(
        relative == root or relative.startswith(root.rstrip("/") + "/")
        for root in roots
    )


def _is_under_src(relative: str) -> bool:
    return relative == "src" or relative.startswith("src/")


def _is_disposable_generated_artifact(relative: str) -> bool:
    parts = Path(relative).parts
    suffix = Path(relative).suffix.lower()
    return (
        "__pycache__" in parts
        or suffix in {".pyc", ".pyo"}
        or any(part.endswith(".egg-info") for part in parts)
    )


def _is_source_generated_artifact(relative: str) -> bool:
    return _is_under_src(relative) and _is_disposable_generated_artifact(relative)


def _is_source_runtime_artifact(relative: str) -> bool:
    if not _is_under_src(relative):
        return False
    return any(
        part.lower() in {"state", "runtime"}
        or Path(part).stem.lower() == "runtime_state"
        for part in Path(relative).parts
    )


def _is_generated_artifact(relative: str, policy: RepositoryPolicy) -> bool:
    return (
        _is_under(relative, policy.generated_roots)
        or _is_source_generated_artifact(relative)
        or _is_source_runtime_artifact(relative)
    )


def _is_ignored(path: Path, root: Path, policy: RepositoryPolicy) -> bool:
    relative_parts = path.relative_to(root).parts
    ignored = set(policy.ignored_parts)
    if any(part in ignored for part in relative_parts):
        top_level_ignored = {
            "artifacts",
            "backtest",
            "data",
            "logs",
            "models",
            "opportunities",
            "orders",
            "reports",
            "secrets",
            "state",
            "tools",
            "wallet",
        }
        if relative_parts[0] in top_level_ignored:
            return True
        return any(part in ignored - top_level_ignored for part in relative_parts)
    return False


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_tracked_files(root: Path) -> set[str]:
    git = shutil.which("git")
    if git is None:
        return set()
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            (git, "ls-files", "-z"),
            cwd=root,
            check=True,
            capture_output=True,
            text=False,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return set()
    return {
        item.decode("utf-8").replace("\\", "/")
        for item in completed.stdout.split(b"\0")
        if item
    }


def _git_has_head(root: Path) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        top_level = subprocess.run(  # noqa: S603  # nosec B603
            (git, "rev-parse", "--show-toplevel"),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if (
            top_level.returncode != 0
            or Path(top_level.stdout.strip()).resolve() != root.resolve()
        ):
            return False
        completed = subprocess.run(  # noqa: S603  # nosec B603
            (git, "rev-parse", "--verify", "HEAD"),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _health_score(findings: tuple[RepositoryValidationFinding, ...]) -> int:
    penalty = 0
    for finding in findings:
        if finding.severity is RepositoryFindingSeverity.CRITICAL:
            penalty += 25
        elif finding.severity is RepositoryFindingSeverity.HIGH:
            penalty += 10
        elif finding.severity is RepositoryFindingSeverity.WARNING:
            penalty += 2
        else:
            penalty += 0
    return max(0, 100 - penalty)


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


if __name__ == "__main__":
    raise SystemExit(main())

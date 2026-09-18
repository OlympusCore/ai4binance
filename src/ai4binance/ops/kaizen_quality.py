"""Read-only Kaizen quality signals for traceable operational improvement."""

from __future__ import annotations

import ast
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    TraceabilityStatus,
    canonical_trace_journal_path,
)
from ai4binance.governance.architecture import (
    DEFAULT_LOGICAL_ARCHITECTURE_REGISTRY_PATH,
    LogicalArchitectureRegistry,
    load_logical_architecture_registry,
)
from ai4binance.governance.enforcement.inventory import (
    EnforcementInventory,
    load_enforcement_inventory,
)
from ai4binance.ops.architecture_migration import (
    ArchitectureMigrationAction,
    ArchitectureMigrationClassification,
    build_architecture_migration_classification,
)
from ai4binance.ops.architecture_projection import CanonicalArchitectureProjection

_FAST_FEEDBACK_COMMANDS = (
    ".venv\\Scripts\\python.exe -B -m pytest tests/test_kaizen_quality.py",
    ".venv\\Scripts\\python.exe -B -m pytest tests/test_auto_audit_loop.py",
    ".venv\\Scripts\\python.exe -B -m pytest tests/test_continuous_assurance.py",
    ".venv\\Scripts\\python.exe -B -m ai4binance.cli vnext-audit --format text",
)
_FULL_GATE_COMMAND = ".\\scripts\\quality.ps1"
_REQUIRED_AUDIT_FIELDS = (
    "event_type",
    "subject_id",
    "subject_sha256",
    "record_sha256",
    "evidence_refs",
    "blockers",
    "execution_allowed",
    "live_eligibility_status",
)
_RUNTIME_RETENTION_CLASSES = {
    "AUDIT_CRITICAL",
    "LATEST_PLUS_RUNS",
    "PROTECTED_PRIVATE",
    "EPHEMERAL",
    "REGENERABLE_CACHE",
    "LOCAL_DATA",
    "LOCAL_MODEL",
    "STAGED_ADMISSION",
    "REVIEW_REQUIRED",
}
_CLOSURE_CHECK_STATUSES = {"PASS", "NOT_VERIFIED", "RUNNING_WITH_BLOCKERS"}
_ARCHITECTURE_HOTSPOT_LINE_THRESHOLD = 1_000
_ARCHITECTURE_HOTSPOT_DEPENDENCY_THRESHOLD = 25
_INSTRUCTION_EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "runtime",
}
_INSTRUCTION_ROOT_FILENAMES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
_CODEX_PROVIDER_INSTRUCTION_PATH = "docs/providers/instruction_codex_provider.md"
_INSTRUCTION_ESTIMATE_STATUS = "TOKEN_ESTIMATE"
_INSTRUCTION_TOKEN_ESTIMATION_METHOD = "WORD_COUNT_X_1_3_CEILING"  # nosec B105  # noqa: S105
_REPRESENTATIVE_INSTRUCTION_CONTEXT_TASKS = (
    ("T1_ROOT_DOCUMENTATION_EDIT", "root_documentation_edit", "README.md"),
    (
        "T2_SRC_PYTHON_IMPLEMENTATION",
        "src_python_implementation",
        "src/ai4binance/application/context/memory.py",
    ),
    (
        "T3_GOVERNANCE_CHANGE",
        "governance_change",
        "src/ai4binance/governance/gate.py",
    ),
    ("T4_RISK_CHANGE", "risk_change", "src/ai4binance/risk.py"),
    (
        "T5_EXECUTION_CHANGE",
        "execution_change",
        "src/ai4binance/execution/order_preview.py",
    ),
    ("T6_TESTS_ONLY_CHANGE", "tests_only_change", "tests/test_kaizen_quality.py"),
    (
        "T7_QUALITY_GATE_SCRIPT_CHANGE",
        "quality_gate_script_change",
        "scripts/quality.ps1",
    ),
    (
        "T8_ARCHITECTURE_DOCUMENTATION",
        "architecture_documentation",
        "docs/architecture/framework_architecture_overview.md",
    ),
)


@dataclass(frozen=True, slots=True)
class RuntimeDirectoryProfile:
    role: str
    retention: str
    privacy_classification: str
    validation_status: str
    retention_class: str
    cleanup_candidate: bool
    cleanup_mode: str | None
    approval_required_for_cleanup: bool
    evidence_critical: bool

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.retention.strip():
            raise ValueError("runtime directory profile requires role and retention")
        if self.validation_status not in {"EXPECTED", "MISSING", "UNKNOWN"}:
            raise ValueError("runtime directory profile validation status is invalid")
        if self.retention_class not in _RUNTIME_RETENTION_CLASSES:
            raise ValueError("runtime directory profile retention class is invalid")
        if self.cleanup_candidate and not self.cleanup_mode:
            raise ValueError("runtime cleanup candidates require a cleanup mode")
        if not self.cleanup_candidate and self.cleanup_mode is not None:
            raise ValueError("runtime cleanup mode requires a cleanup candidate")


_RUNTIME_DIRECTORY_PROFILES: dict[str, RuntimeDirectoryProfile] = {
    "runtime/artifacts": RuntimeDirectoryProfile(
        role="generated evidence",
        retention="retain according to evidence family",
        privacy_classification=(
            "internal evidence; redact private payloads before public reporting"
        ),
        validation_status="EXPECTED",
        retention_class="AUDIT_CRITICAL",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/quality": RuntimeDirectoryProfile(
        role="quality gate evidence",
        retention="retain latest summaries and run-scoped logs",
        privacy_classification="internal quality evidence",
        validation_status="EXPECTED",
        retention_class="LATEST_PLUS_RUNS",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/reports": RuntimeDirectoryProfile(
        role="generated human-readable reports",
        retention="retain report families by audit value",
        privacy_classification=(
            "public-safe only after privacy and financial leak guards pass"
        ),
        validation_status="EXPECTED",
        retention_class="LATEST_PLUS_RUNS",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/state": RuntimeDirectoryProfile(
        role="mutable runtime state",
        retention="retain current state and governed journals",
        privacy_classification="private state must stay under runtime/state/private",
        validation_status="EXPECTED",
        retention_class="PROTECTED_PRIVATE",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/logs": RuntimeDirectoryProfile(
        role="runtime audit and operational logs",
        retention="retain bounded logs with audit-critical lineage",
        privacy_classification="internal logs; never include secrets",
        validation_status="EXPECTED",
        retention_class="AUDIT_CRITICAL",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/tmp": RuntimeDirectoryProfile(
        role="ephemeral temporary files",
        retention="cleanup candidate after process/test ownership is clear",
        privacy_classification="must not contain credentials or canonical evidence",
        validation_status="EXPECTED",
        retention_class="EPHEMERAL",
        cleanup_candidate=True,
        cleanup_mode="review-only test and process temporary retention",
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/data": RuntimeDirectoryProfile(
        role="local runtime datasets",
        retention="retain by dataset revision and provenance",
        privacy_classification="market data and local-only datasets",
        validation_status="EXPECTED",
        retention_class="LOCAL_DATA",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/models": RuntimeDirectoryProfile(
        role="local model artifacts",
        retention="retain by model registry and reproducibility value",
        privacy_classification="local-only model files",
        validation_status="EXPECTED",
        retention_class="LOCAL_MODEL",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/cache": RuntimeDirectoryProfile(
        role="runtime cache",
        retention="cleanup candidate when reproducible",
        privacy_classification="must not contain secrets",
        validation_status="EXPECTED",
        retention_class="REGENERABLE_CACHE",
        cleanup_candidate=True,
        cleanup_mode="review-only reproducible cache retention",
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/uv-cache": RuntimeDirectoryProfile(
        role="tool cache",
        retention="cleanup candidate when tooling can regenerate it",
        privacy_classification="dependency cache; keep outside source",
        validation_status="EXPECTED",
        retention_class="REGENERABLE_CACHE",
        cleanup_candidate=True,
        cleanup_mode="review-only reproducible tool cache retention",
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/skill_staging": RuntimeDirectoryProfile(
        role="controlled skill staging",
        retention="retain active admissions and audit records",
        privacy_classification="local staged skill evidence",
        validation_status="EXPECTED",
        retention_class="STAGED_ADMISSION",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/test": RuntimeDirectoryProfile(
        role="runtime test evidence",
        retention="cleanup candidate after test ownership and evidence value are clear",
        privacy_classification="test evidence only",
        validation_status="EXPECTED",
        retention_class="EPHEMERAL",
        cleanup_candidate=True,
        cleanup_mode="review-only test evidence retention",
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/audit": RuntimeDirectoryProfile(
        role="runtime audit evidence",
        retention="retain audit-critical records",
        privacy_classification="internal audit evidence",
        validation_status="EXPECTED",
        retention_class="AUDIT_CRITICAL",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
    "runtime/analysis": RuntimeDirectoryProfile(
        role="local analysis output",
        retention="retain only when linked to evidence refs",
        privacy_classification="research-only analysis output",
        validation_status="EXPECTED",
        retention_class="LATEST_PLUS_RUNS",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/dashboard": RuntimeDirectoryProfile(
        role="generated local dashboard deployment",
        retention="redeploy from canonical tracked source; preserve private profile",
        privacy_classification=(
            "browser profile is protected private state and must never be archived"
        ),
        validation_status="EXPECTED",
        retention_class="PROTECTED_PRIVATE",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/dashboard/browser-profile": RuntimeDirectoryProfile(
        role="private local dashboard browser profile",
        retention=(
            "preserve while installed; never archive, inspect, or clean generically"
        ),
        privacy_classification="protected private browser state",
        validation_status="EXPECTED",
        retention_class="PROTECTED_PRIVATE",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=False,
    ),
    "runtime/artifacts/maintenance_archive": RuntimeDirectoryProfile(
        role="maintenance archive and cleanup receipts",
        retention="retain by explicit archive policy and capacity review",
        privacy_classification="internal archive; access errors require review",
        validation_status="EXPECTED",
        retention_class="AUDIT_CRITICAL",
        cleanup_candidate=False,
        cleanup_mode=None,
        approval_required_for_cleanup=True,
        evidence_critical=True,
    ),
}


@dataclass(frozen=True, slots=True)
class KaizenBlockerSignal:
    blocker: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int
    age_seconds: int
    state: str
    evidence_ref: str
    proof_command: str
    recommended_action_ref: str

    def __post_init__(self) -> None:
        if not self.blocker.strip():
            raise ValueError("kaizen blocker is required")
        if self.occurrences < 1 or self.age_seconds < 0:
            raise ValueError("kaizen blocker age and occurrences must be valid")
        if self.state not in {"NEW", "PERSISTENT", "RESOLVED"}:
            raise ValueError("kaizen blocker state is invalid")
        if not self.evidence_ref.strip() or not self.proof_command.strip():
            raise ValueError("kaizen blocker evidence and proof command are required")

    def to_payload(self) -> dict[str, object]:
        return {
            "blocker": self.blocker,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "occurrences": self.occurrences,
            "age_seconds": self.age_seconds,
            "state": self.state,
            "evidence_ref": self.evidence_ref,
            "proof_command": self.proof_command,
            "recommended_action_ref": self.recommended_action_ref,
        }


@dataclass(frozen=True, slots=True)
class KaizenTraceabilityMatrixRow:
    entrypoint_id: str
    policy_source: str
    tests: tuple[str, ...]
    evidence_ref: str
    canonical_trace_ref: str
    coverage_state: str
    traceability_status: str

    def __post_init__(self) -> None:
        if not self.entrypoint_id.strip():
            raise ValueError("kaizen traceability entrypoint is required")
        if not self.policy_source.strip() or not self.tests:
            raise ValueError("kaizen traceability source and tests are required")
        if self.traceability_status not in {"RECORDED", "REQUIRED_NOT_RECORDED"}:
            raise ValueError("kaizen traceability status is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "entrypoint_id": self.entrypoint_id,
            "policy_source": self.policy_source,
            "tests": list(self.tests),
            "evidence_ref": self.evidence_ref,
            "canonical_trace_ref": self.canonical_trace_ref,
            "coverage_state": self.coverage_state,
            "traceability_status": self.traceability_status,
        }


@dataclass(frozen=True, slots=True)
class KaizenAuditContractCheck:
    contract_id: str
    status: str
    missing_fields: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.contract_id.strip():
            raise ValueError("kaizen audit contract id is required")
        if self.status not in {"PASS", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("kaizen audit contract status is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "status": self.status,
            "missing_fields": list(self.missing_fields),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class RuntimeDirectoryClassification:
    path: str
    present: bool
    role: str
    retention: str
    privacy_classification: str
    validation_status: str
    retention_class: str
    cleanup_candidate: bool
    cleanup_mode: str | None
    approval_required_for_cleanup: bool
    evidence_critical: bool
    observed_children: tuple[str, ...] = ()
    scanned_file_count: int = 0
    scanned_total_bytes: int = 0
    oldest_modified_at: str | None = None
    newest_modified_at: str | None = None
    scan_truncated: bool = False
    access_errors: tuple[str, ...] = ()
    source_like_file_count: int = 0
    non_markdown_report_count: int = 0
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.path.startswith("runtime/"):
            raise ValueError("runtime inventory path must be under runtime")
        if self.validation_status not in {"EXPECTED", "MISSING", "UNKNOWN"}:
            raise ValueError("runtime inventory validation status is invalid")
        if self.retention_class not in _RUNTIME_RETENTION_CLASSES:
            raise ValueError("runtime inventory retention class is invalid")
        if self.cleanup_candidate and not self.cleanup_mode:
            raise ValueError("runtime cleanup candidates require a cleanup mode")
        if not self.cleanup_candidate and self.cleanup_mode is not None:
            raise ValueError("runtime cleanup mode requires a cleanup candidate")
        if self.cleanup_candidate and not self.approval_required_for_cleanup:
            raise ValueError("runtime cleanup candidates require explicit approval")
        if self.scanned_file_count < 0 or self.scanned_total_bytes < 0:
            raise ValueError("runtime inventory metrics cannot be negative")

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "present": self.present,
            "role": self.role,
            "retention": self.retention,
            "privacy_classification": self.privacy_classification,
            "validation_status": self.validation_status,
            "retention_class": self.retention_class,
            "cleanup_candidate": self.cleanup_candidate,
            "cleanup_mode": self.cleanup_mode,
            "approval_required_for_cleanup": self.approval_required_for_cleanup,
            "evidence_critical": self.evidence_critical,
            "observed_children": list(self.observed_children),
            "scanned_file_count": self.scanned_file_count,
            "scanned_total_bytes": self.scanned_total_bytes,
            "oldest_modified_at": self.oldest_modified_at,
            "newest_modified_at": self.newest_modified_at,
            "scan_truncated": self.scan_truncated,
            "access_errors": list(self.access_errors),
            "source_like_file_count": self.source_like_file_count,
            "non_markdown_report_count": self.non_markdown_report_count,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class RuntimeInventorySnapshot:
    root: str
    classifications: tuple[RuntimeDirectoryClassification, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "root": self.root,
            "classifications": [
                classification.to_payload() for classification in self.classifications
            ],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ArchitectureModuleBaseline:
    """Read-only static dependency measurements for one source module."""

    path: str
    line_count: int
    internal_dependencies: tuple[str, ...]
    internal_dependents: tuple[str, ...]
    fan_in: int
    test_owners: tuple[str, ...]
    hotspot_reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line_count": self.line_count,
            "internal_dependencies": list(self.internal_dependencies),
            "internal_dependents": list(self.internal_dependents),
            "fan_out": len(self.internal_dependencies),
            "fan_in": self.fan_in,
            "test_owners": list(self.test_owners),
            "hotspot_reasons": list(self.hotspot_reasons),
        }


@dataclass(frozen=True, slots=True)
class ArchitectureBaseline:
    """Evidence-only architecture baseline; it cannot authorize refactoring."""

    source_root: str
    module_count: int
    source_line_count: int
    modules: tuple[ArchitectureModuleBaseline, ...]
    import_cycles: tuple[tuple[str, ...], ...]
    migration_ledger: tuple[ArchitectureMigrationClassification, ...]

    def to_payload(self) -> dict[str, object]:
        action_counts = Counter(
            item.classification.value for item in self.migration_ledger
        )
        target_sources: dict[str, list[ArchitectureMigrationClassification]] = {}
        for classification in self.migration_ledger:
            for target_path in classification.target_paths:
                if target_path.endswith(".py"):
                    target_sources.setdefault(target_path, []).append(classification)
        target_path_collisions = [
            {
                "target_path": target_path,
                "source_paths": [item.source_path for item in classifications],
                "classifications": [
                    item.classification.value for item in classifications
                ],
                "status": _target_path_collision_status(classifications),
            }
            for target_path, classifications in sorted(target_sources.items())
            if len(classifications) > 1
        ]
        return {
            "source_root": self.source_root,
            "module_count": self.module_count,
            "source_line_count": self.source_line_count,
            "modules": [module.to_payload() for module in self.modules],
            "import_cycles": [list(cycle) for cycle in self.import_cycles],
            "migration_ledger": [
                classification.to_payload() for classification in self.migration_ledger
            ],
            "migration_action_counts": {
                action.value: action_counts[action.value]
                for action in ArchitectureMigrationAction
            },
            "classification_coverage": {
                "classified_module_count": len(self.migration_ledger),
                "unclassified_module_count": max(
                    self.module_count - len(self.migration_ledger), 0
                ),
                "coverage_percent": (
                    round(len(self.migration_ledger) * 100 / self.module_count, 2)
                    if self.module_count
                    else 100.0
                ),
                "allowed_actions": [
                    action.value for action in ArchitectureMigrationAction
                ],
            },
            "target_path_collisions": target_path_collisions,
            "hotspots": [
                module.path for module in self.modules if module.hotspot_reasons
            ],
        }


def _target_path_collision_status(
    classifications: list[ArchitectureMigrationClassification],
) -> str:
    actions = {item.classification for item in classifications}
    if actions == {ArchitectureMigrationAction.MERGE}:
        return "EXPECTED_MERGE"
    if ArchitectureMigrationAction.FACADE in actions and actions <= {
        ArchitectureMigrationAction.FACADE,
        ArchitectureMigrationAction.KEEP,
        ArchitectureMigrationAction.MOVE,
    }:
        return "EXPECTED_FACADE"
    return "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class InstructionDocumentBaseline:
    """Read-only inventory measurements for one repository instruction document."""

    path: str
    scope: str
    byte_count: int
    line_count: int
    word_count: int
    estimated_token_count: int
    section_count: int
    authority_scope: str | None
    canonical_references: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "scope": self.scope,
            "byte_count": self.byte_count,
            "line_count": self.line_count,
            "word_count": self.word_count,
            "estimated_token_count": self.estimated_token_count,
            "section_count": self.section_count,
            "authority_scope": self.authority_scope,
            "canonical_references": list(self.canonical_references),
        }


@dataclass(frozen=True, slots=True)
class InstructionOverlap:
    """Deterministic exact-block overlap for advisory instruction Kaizen evidence."""

    left_path: str
    right_path: str
    shared_block_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "left_path": self.left_path,
            "right_path": self.right_path,
            "shared_block_count": self.shared_block_count,
        }


@dataclass(frozen=True, slots=True)
class InstructionBaseline:
    """Evidence-only instruction footprint; it cannot alter policy or authority."""

    documents: tuple[InstructionDocumentBaseline, ...]
    overlaps: tuple[InstructionOverlap, ...]
    unreadable_paths: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "instruction_file_count": len(self.documents),
            "scoped_instruction_file_count": sum(
                document.scope == "SCOPED" for document in self.documents
            ),
            "total_byte_count": sum(document.byte_count for document in self.documents),
            "total_line_count": sum(document.line_count for document in self.documents),
            "total_word_count": sum(document.word_count for document in self.documents),
            "estimated_total_token_count": sum(
                document.estimated_token_count for document in self.documents
            ),
            "documents": [document.to_payload() for document in self.documents],
            "exact_block_overlaps": [overlap.to_payload() for overlap in self.overlaps],
            "unreadable_paths": list(self.unreadable_paths),
            "status": "READY" if not self.unreadable_paths else "RUNNING_WITH_BLOCKERS",
        }


@dataclass(frozen=True, slots=True)
class InstructionContextMeasurement:
    """Persistent Codex instruction cost for one representative task."""

    task_id: str
    task_type: str
    working_path: str
    instruction_paths: tuple[str, ...]
    instruction_bytes: int
    estimated_instruction_tokens: int
    exact_block_overlap_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "working_path": self.working_path,
            "instruction_paths": list(self.instruction_paths),
            "instruction_bytes": self.instruction_bytes,
            "estimated_instruction_tokens": self.estimated_instruction_tokens,
            "exact_block_overlap_count": self.exact_block_overlap_count,
            "token_count_status": _INSTRUCTION_ESTIMATE_STATUS,
        }


@dataclass(frozen=True, slots=True)
class InstructionContextBenchmark:
    """Evidence-only Codex context benchmark; it is not routing authority."""

    status: str
    measurements: tuple[InstructionContextMeasurement, ...]
    blockers: tuple[str, ...]
    token_estimation_method: str = _INSTRUCTION_TOKEN_ESTIMATION_METHOD
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("instruction context benchmark status is invalid")
        if self.status == "READY" and (self.blockers or not self.measurements):
            raise ValueError(
                "ready instruction context benchmark requires measurements"
            )
        if self.status == "RUNNING_WITH_BLOCKERS" and not self.blockers:
            raise ValueError("blocked instruction context benchmark requires blockers")
        if self.token_estimation_method != _INSTRUCTION_TOKEN_ESTIMATION_METHOD:
            raise ValueError("instruction context token estimation method is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("instruction context benchmark cannot authorize trading")

    @property
    def max_instruction_bytes(self) -> int:
        return max(
            (measurement.instruction_bytes for measurement in self.measurements),
            default=0,
        )

    @property
    def max_estimated_instruction_tokens(self) -> int:
        return max(
            (
                measurement.estimated_instruction_tokens
                for measurement in self.measurements
            ),
            default=0,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "measurement_type": "PERSISTENT_INSTRUCTION_CONTEXT",
            "token_count_status": _INSTRUCTION_ESTIMATE_STATUS,
            "token_estimation_method": self.token_estimation_method,
            "representative_task_count": len(self.measurements),
            "max_instruction_bytes": self.max_instruction_bytes,
            "max_estimated_instruction_tokens": (self.max_estimated_instruction_tokens),
            "measurements": [
                measurement.to_payload() for measurement in self.measurements
            ],
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class RuntimeKaizenClosureCheck:
    check_id: str
    status: str
    evidence_ref: str
    proof_command: str
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.check_id.strip():
            raise ValueError("runtime kaizen closure check id is required")
        if self.status not in _CLOSURE_CHECK_STATUSES:
            raise ValueError("runtime kaizen closure check status is invalid")
        if not self.evidence_ref.strip() or not self.proof_command.strip():
            raise ValueError("runtime kaizen closure check evidence is required")
        if self.status == "PASS" and self.blockers:
            raise ValueError("passing runtime kaizen closure checks cannot block")
        if self.status != "PASS" and not self.blockers:
            raise ValueError("non-passing runtime kaizen closure checks must block")

    def to_payload(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "evidence_ref": self.evidence_ref,
            "proof_command": self.proof_command,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class GovernanceApprovalEvidence:
    """Read-only approval evidence derived from a governance-gate payload."""

    change_class: str
    status: str
    required_approval_count: int
    observed_approval_count: int
    hard_veto: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.change_class.strip():
            raise ValueError("governance approval evidence change class is required")
        if self.status not in {
            "PASS",
            "NOT_REQUIRED",
            "NOT_VERIFIED",
            "RUNNING_WITH_BLOCKERS",
        }:
            raise ValueError("governance approval evidence status is invalid")
        if self.required_approval_count < 0 or self.observed_approval_count < 0:
            raise ValueError("governance approval counts must be non-negative")
        if self.status == "PASS" and (self.hard_veto or self.blockers):
            raise ValueError("passing governance approval evidence cannot block")
        if self.status == "NOT_REQUIRED" and (
            self.hard_veto
            or self.blockers
            or self.required_approval_count
            or self.observed_approval_count
        ):
            raise ValueError("not-required governance approval evidence is invalid")
        if self.status in {"NOT_VERIFIED", "RUNNING_WITH_BLOCKERS"} and (
            not self.hard_veto or not self.blockers
        ):
            raise ValueError("blocked governance approval evidence requires a veto")

    def to_payload(self) -> dict[str, object]:
        return {
            "change_class": self.change_class,
            "status": self.status,
            "required_approval_count": self.required_approval_count,
            "observed_approval_count": self.observed_approval_count,
            "hard_veto": self.hard_veto,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class CurrentGateEvidence:
    """Read-only current gate evidence accepted only after coherence checks."""

    quality_gate_payload: dict[str, object] | None
    governance_gate_payload: dict[str, object] | None
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        has_quality_payload = self.quality_gate_payload is not None
        has_governance_payload = self.governance_gate_payload is not None
        if has_quality_payload != has_governance_payload:
            raise ValueError("current gate evidence requires both payloads")
        if self.blockers and (has_quality_payload or has_governance_payload):
            raise ValueError("accepted current gate evidence cannot block")
        if not self.blockers and not (has_quality_payload and has_governance_payload):
            raise ValueError("missing current gate evidence must be visible")


@dataclass(frozen=True, slots=True)
class RuntimeKaizenClosureGate:
    status: str
    technical_quality_status: str
    governance_closure_status: str
    acceptance_status: str
    governance_approval_evidence: GovernanceApprovalEvidence
    checks: tuple[RuntimeKaizenClosureCheck, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("runtime kaizen closure gate status is invalid")
        if self.acceptance_status not in {"ACCEPTANCE_READY", "ACCEPTANCE_BLOCKED"}:
            raise ValueError("runtime kaizen closure acceptance status is invalid")
        if not self.checks:
            raise ValueError("runtime kaizen closure gate requires checks")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("runtime kaizen closure gate cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "technical_quality_status": self.technical_quality_status,
            "governance_closure_status": self.governance_closure_status,
            "acceptance_status": self.acceptance_status,
            "governance_approval_evidence": (
                self.governance_approval_evidence.to_payload()
            ),
            "checks": [check.to_payload() for check in self.checks],
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class KaizenQualitySnapshot:
    snapshot_id: str
    observed_at: datetime
    status: str
    blocker_signals: tuple[KaizenBlockerSignal, ...]
    traceability_matrix: tuple[KaizenTraceabilityMatrixRow, ...]
    audit_contract_checks: tuple[KaizenAuditContractCheck, ...]
    runtime_inventory: RuntimeInventorySnapshot
    architecture_baseline: ArchitectureBaseline
    instruction_baseline: InstructionBaseline
    instruction_context_benchmark: InstructionContextBenchmark
    closure_gate: RuntimeKaizenClosureGate
    fast_feedback_commands: tuple[str, ...]
    full_gate_command: str
    closure_entrypoint_order: tuple[str, ...]
    blockers: tuple[str, ...]
    architecture_projection: CanonicalArchitectureProjection | None = None
    logical_architecture_registry: LogicalArchitectureRegistry | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("kaizen snapshot id is required")
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("kaizen snapshot status is invalid")
        if not self.fast_feedback_commands or not self.full_gate_command.strip():
            raise ValueError("kaizen snapshot requires verification commands")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("kaizen quality snapshot cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status,
            "blocker_signals": [signal.to_payload() for signal in self.blocker_signals],
            "traceability_matrix": [
                row.to_payload() for row in self.traceability_matrix
            ],
            "audit_contract_checks": [
                check.to_payload() for check in self.audit_contract_checks
            ],
            "runtime_inventory": self.runtime_inventory.to_payload(),
            "architecture_baseline": self.architecture_baseline.to_payload(),
            "architecture_projection": {
                "status": (
                    "AVAILABLE"
                    if self.architecture_projection is not None
                    else "NOT_PROVIDED"
                ),
                "projection": (
                    self.architecture_projection.to_payload()
                    if self.architecture_projection is not None
                    else None
                ),
            },
            "logical_architecture_registry": {
                "status": (
                    "AVAILABLE"
                    if self.logical_architecture_registry is not None
                    else "NOT_PROVIDED"
                ),
                "registry": (
                    self.logical_architecture_registry.to_payload()
                    if self.logical_architecture_registry is not None
                    else None
                ),
            },
            "instruction_baseline": self.instruction_baseline.to_payload(),
            "instruction_context_benchmark": (
                self.instruction_context_benchmark.to_payload()
            ),
            "closure_gate": self.closure_gate.to_payload(),
            "fast_feedback_commands": list(self.fast_feedback_commands),
            "full_gate_command": self.full_gate_command,
            "closure_entrypoint_order": list(self.closure_entrypoint_order),
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_kaizen_quality_snapshot(
    *,
    observed_at: datetime,
    blocker_cycles: tuple[tuple[datetime, tuple[str, ...]], ...],
    repository_root: Path,
    continuous_assurance_payload: dict[str, object] | None = None,
    quality_gate_payload: dict[str, object] | None = None,
    governance_gate_payload: dict[str, object] | None = None,
    gate_evidence_blockers: tuple[str, ...] = (),
    inventory: EnforcementInventory | None = None,
    trace_journal: CanonicalTraceJournal | None = None,
    architecture_projection: CanonicalArchitectureProjection | None = None,
    logical_architecture_registry: LogicalArchitectureRegistry | None = None,
) -> KaizenQualitySnapshot:
    """Build a report-only improvement snapshot from local evidence."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("kaizen snapshot timestamp must be timezone-aware")
    loaded_inventory = inventory
    inventory_blockers: tuple[str, ...] = ()
    if loaded_inventory is None:
        try:
            loaded_inventory = load_enforcement_inventory(
                repository_root / "config" / "governance" / "enforcement_inventory.yaml"
            )
        except (OSError, ValueError) as exc:
            inventory_blockers = (f"ENFORCEMENT_INVENTORY_UNAVAILABLE:{exc}",)
    loaded_logical_architecture_registry = logical_architecture_registry
    logical_architecture_blockers: tuple[str, ...] = ()
    registry_path = repository_root / DEFAULT_LOGICAL_ARCHITECTURE_REGISTRY_PATH
    if loaded_logical_architecture_registry is None and registry_path.is_file():
        try:
            loaded_logical_architecture_registry = load_logical_architecture_registry(
                registry_path,
                repository_root=repository_root,
            )
        except ValueError as exc:
            logical_architecture_blockers = (
                f"LOGICAL_ARCHITECTURE_REGISTRY_UNAVAILABLE:{exc}",
            )
    journal = trace_journal or CanonicalTraceJournal(
        canonical_trace_journal_path(repository_root)
    )
    blocker_signals = _blocker_signals(blocker_cycles)
    traceability_matrix, traceability_blockers = _traceability_matrix(
        loaded_inventory,
        journal,
    )
    audit_checks = _audit_contract_checks(continuous_assurance_payload)
    runtime_inventory = _runtime_inventory(repository_root)
    architecture_baseline = build_architecture_baseline(repository_root)
    instruction_baseline = build_instruction_baseline(repository_root)
    instruction_context_benchmark = build_instruction_context_benchmark(
        repository_root,
        instruction_baseline=instruction_baseline,
    )
    audit_blockers = tuple(
        blocker for check in audit_checks for blocker in check.blockers
    )
    closure_order = _closure_entrypoint_order(loaded_inventory)
    closure_gate = _runtime_kaizen_closure_gate(
        runtime_inventory=runtime_inventory,
        fast_feedback_commands=_FAST_FEEDBACK_COMMANDS,
        full_gate_command=_FULL_GATE_COMMAND,
        quality_gate_payload=quality_gate_payload,
        governance_gate_payload=governance_gate_payload,
        gate_evidence_blockers=gate_evidence_blockers,
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *inventory_blockers,
                *logical_architecture_blockers,
                *traceability_blockers,
                *audit_blockers,
                *runtime_inventory.blockers,
                *closure_gate.blockers,
                *(
                    "KAIZEN_PERSISTENT_BLOCKERS_PRESENT"
                    for signal in blocker_signals
                    if signal.state == "PERSISTENT"
                ),
            )
        )
    )
    return KaizenQualitySnapshot(
        snapshot_id=f"kaizen-quality:{int(observed_at.timestamp())}",
        observed_at=observed_at,
        status="READY" if not blockers else "RUNNING_WITH_BLOCKERS",
        blocker_signals=blocker_signals,
        traceability_matrix=traceability_matrix,
        audit_contract_checks=audit_checks,
        runtime_inventory=runtime_inventory,
        architecture_baseline=architecture_baseline,
        architecture_projection=architecture_projection,
        logical_architecture_registry=loaded_logical_architecture_registry,
        instruction_baseline=instruction_baseline,
        instruction_context_benchmark=instruction_context_benchmark,
        closure_gate=closure_gate,
        fast_feedback_commands=_FAST_FEEDBACK_COMMANDS,
        full_gate_command=_FULL_GATE_COMMAND,
        closure_entrypoint_order=closure_order,
        blockers=blockers,
    )


def load_current_gate_evidence(repository_root: Path) -> CurrentGateEvidence:
    """Load coherent current gate evidence without granting execution authority."""
    gate_directory = repository_root / "runtime" / "artifacts" / "quality" / "gate"
    quality_payload, quality_blocker = _load_current_gate_json_object(
        gate_directory / "deterministic_quality_gate_latest.json",
        unavailable_blocker="CURRENT_QUALITY_GATE_EVIDENCE_UNAVAILABLE",
        malformed_blocker="CURRENT_QUALITY_GATE_EVIDENCE_MALFORMED",
    )
    governance_payload, governance_blocker = _load_current_gate_json_object(
        gate_directory / "governance_gate_latest.json",
        unavailable_blocker="CURRENT_GOVERNANCE_GATE_EVIDENCE_UNAVAILABLE",
        malformed_blocker="CURRENT_GOVERNANCE_GATE_EVIDENCE_MALFORMED",
    )
    unavailable_blockers = tuple(
        blocker for blocker in (quality_blocker, governance_blocker) if blocker
    )
    if unavailable_blockers:
        return CurrentGateEvidence(None, None, unavailable_blockers)
    if quality_payload is None or governance_payload is None:
        return CurrentGateEvidence(
            None,
            None,
            ("CURRENT_GATE_EVIDENCE_UNAVAILABLE",),
        )
    quality_subject = _current_gate_subject_sha256(quality_payload)
    governance_subject = _current_gate_subject_sha256(governance_payload)
    if not quality_subject or quality_subject != governance_subject:
        return CurrentGateEvidence(
            None,
            None,
            ("CURRENT_GATE_EVIDENCE_SUBJECT_MISMATCH",),
        )
    if not (
        _current_gate_payload_is_fail_closed(quality_payload)
        and _current_gate_payload_is_fail_closed(governance_payload)
    ):
        return CurrentGateEvidence(
            None,
            None,
            ("CURRENT_GATE_EVIDENCE_SAFETY_STATE_INVALID",),
        )
    return CurrentGateEvidence(quality_payload, governance_payload, ())


def _load_current_gate_json_object(
    path: Path,
    *,
    unavailable_blocker: str,
    malformed_blocker: str,
) -> tuple[dict[str, object] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, unavailable_blocker
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, malformed_blocker
    if not isinstance(payload, dict):
        return None, malformed_blocker
    return payload, None


def _current_gate_subject_sha256(payload: dict[str, object]) -> str | None:
    subject_digest = payload.get("subject_digest")
    if not isinstance(subject_digest, dict):
        return None
    subject_sha256 = subject_digest.get("subject_sha256")
    return subject_sha256 if isinstance(subject_sha256, str) else None


def _current_gate_payload_is_fail_closed(payload: dict[str, object]) -> bool:
    return (
        payload.get("execution_allowed") is False
        and payload.get("promotion_status") == "RESEARCH_ONLY"
        and payload.get("live_eligibility_status") == "LIVE_ORDER_BLOCKED"
    )


def build_architecture_baseline(repository_root: Path) -> ArchitectureBaseline:
    """Measure local module size and imports without modifying repository state."""
    source_root = repository_root / "src" / "ai4binance"
    if not source_root.is_dir():
        return ArchitectureBaseline(
            source_root="src/ai4binance",
            module_count=0,
            source_line_count=0,
            modules=(),
            import_cycles=(),
            migration_ledger=(),
        )
    source_paths = tuple(sorted(source_root.rglob("*.py")))
    module_names = {
        _source_module_name(source_root, source_path): source_path
        for source_path in source_paths
    }
    dependencies = {
        module_name: _internal_imports(
            source_path=source_path,
            module_name=module_name,
            module_names=module_names,
        )
        for module_name, source_path in module_names.items()
    }
    fan_in = Counter(
        dependency
        for module_dependencies in dependencies.values()
        for dependency in module_dependencies
    )
    dependents = {
        module_name: tuple(
            sorted(
                owner
                for owner, owner_dependencies in dependencies.items()
                if module_name in owner_dependencies
            )
        )
        for module_name in module_names
    }
    test_text_by_path = _test_text_by_path(repository_root)
    module_baselines = {
        module_name: _architecture_module_baseline(
            source_root=source_root,
            source_path=source_path,
            module_name=module_name,
            dependencies=dependencies[module_name],
            dependents=dependents[module_name],
            fan_in=fan_in[module_name],
            test_text_by_path=test_text_by_path,
        )
        for module_name, source_path in sorted(module_names.items())
    }
    modules = tuple(module_baselines.values())
    migration_ledger = tuple(
        build_architecture_migration_classification(
            source_root=source_root,
            source_path=source_path,
            baseline=module_baselines[module_name],
        )
        for module_name, source_path in sorted(module_names.items())
    )
    return ArchitectureBaseline(
        source_root="src/ai4binance",
        module_count=len(modules),
        source_line_count=sum(module.line_count for module in modules),
        modules=modules,
        import_cycles=_import_cycles(dependencies),
        migration_ledger=migration_ledger,
    )


def build_instruction_baseline(repository_root: Path) -> InstructionBaseline:
    """Measure instruction files and exact repeated blocks without policy changes."""
    unreadable_paths: list[str] = []
    paths = _instruction_document_paths(repository_root, unreadable_paths)
    documents: list[InstructionDocumentBaseline] = []
    blocks_by_path: dict[str, frozenset[str]] = {}
    for path in paths:
        relative_path = path.relative_to(repository_root).as_posix()
        try:
            content = path.read_bytes()
            text = content.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable_paths.append(relative_path)
            continue
        documents.append(
            InstructionDocumentBaseline(
                path=relative_path,
                scope=_instruction_scope(path, repository_root),
                byte_count=len(content),
                line_count=len(text.splitlines()),
                word_count=len(text.split()),
                estimated_token_count=_estimated_token_count(text),
                section_count=sum(
                    line.lstrip().startswith("#") for line in text.splitlines()
                ),
                authority_scope=_frontmatter_value(text, "authority_scope"),
                canonical_references=_canonical_references(text),
            )
        )
        blocks_by_path[relative_path] = _normalized_instruction_blocks(text)
    overlaps = tuple(
        InstructionOverlap(
            left_path=left_path,
            right_path=right_path,
            shared_block_count=len(
                blocks_by_path[left_path] & blocks_by_path[right_path]
            ),
        )
        for index, left_path in enumerate(sorted(blocks_by_path))
        for right_path in sorted(blocks_by_path)[index + 1 :]
        if blocks_by_path[left_path] & blocks_by_path[right_path]
    )
    return InstructionBaseline(
        documents=tuple(sorted(documents, key=lambda document: document.path)),
        overlaps=overlaps,
        unreadable_paths=tuple(sorted(set(unreadable_paths))),
    )


def build_instruction_context_benchmark(
    repository_root: Path,
    *,
    instruction_baseline: InstructionBaseline | None = None,
) -> InstructionContextBenchmark:
    """Measure representative persistent Codex chains without invoking an LLM."""
    baseline = instruction_baseline or build_instruction_baseline(repository_root)
    documents_by_path = {document.path: document for document in baseline.documents}
    required_paths = ("AGENTS.md", _CODEX_PROVIDER_INSTRUCTION_PATH)
    blockers = [
        f"INSTRUCTION_CONTEXT_UNREADABLE:{path}" for path in baseline.unreadable_paths
    ]
    blockers.extend(
        f"INSTRUCTION_CONTEXT_REQUIRED_DOCUMENT_MISSING:{path}"
        for path in required_paths
        if path not in documents_by_path
    )
    if blockers:
        return InstructionContextBenchmark(
            status="RUNNING_WITH_BLOCKERS",
            measurements=(),
            blockers=tuple(sorted(set(blockers))),
        )

    scoped_documents = tuple(
        document for document in baseline.documents if document.scope == "SCOPED"
    )
    measurements: list[InstructionContextMeasurement] = []
    for task_id, task_type, working_path in _REPRESENTATIVE_INSTRUCTION_CONTEXT_TASKS:
        instruction_paths = list(required_paths)
        matching_scopes = tuple(
            document
            for document in scoped_documents
            if _instruction_scope_contains(document.path, working_path)
        )
        if matching_scopes:
            nearest_scope = max(
                matching_scopes,
                key=lambda document: len(PurePosixPath(document.path).parent.parts),
            )
            instruction_paths.append(nearest_scope.path)
        selected_documents = tuple(
            documents_by_path[path] for path in instruction_paths
        )
        selected_path_set = set(instruction_paths)
        measurements.append(
            InstructionContextMeasurement(
                task_id=task_id,
                task_type=task_type,
                working_path=working_path,
                instruction_paths=tuple(instruction_paths),
                instruction_bytes=sum(
                    document.byte_count for document in selected_documents
                ),
                estimated_instruction_tokens=sum(
                    document.estimated_token_count for document in selected_documents
                ),
                exact_block_overlap_count=sum(
                    overlap.shared_block_count
                    for overlap in baseline.overlaps
                    if overlap.left_path in selected_path_set
                    and overlap.right_path in selected_path_set
                ),
            )
        )
    return InstructionContextBenchmark(
        status="READY",
        measurements=tuple(measurements),
        blockers=(),
    )


def _instruction_scope_contains(
    scoped_instruction_path: str, working_path: str
) -> bool:
    scope_path = PurePosixPath(scoped_instruction_path).parent
    target_path = PurePosixPath(working_path)
    return target_path == scope_path or scope_path in target_path.parents


def _instruction_document_paths(
    repository_root: Path,
    unreadable_paths: list[str],
) -> tuple[Path, ...]:
    paths = {
        repository_root / filename
        for filename in _INSTRUCTION_ROOT_FILENAMES
        if (repository_root / filename).is_file()
    }
    for relative_path in (
        "docs/governance/instruction_core_custom_instructions.md",
        "docs/providers/instruction_codex_provider.md",
        "docs/providers/instruction_claude_provider.md",
    ):
        path = repository_root / relative_path
        if path.is_file():
            paths.add(path)

    def on_error(error: OSError) -> None:
        try:
            unreadable_paths.append(
                Path(error.filename or "instruction-discovery")
                .relative_to(repository_root)
                .as_posix()
            )
        except ValueError:
            unreadable_paths.append("instruction-discovery")

    for directory, child_directories, filenames in os.walk(
        repository_root,
        topdown=True,
        onerror=on_error,
    ):
        child_directories[:] = [
            child
            for child in child_directories
            if child not in _INSTRUCTION_EXCLUDED_DIRECTORIES
        ]
        if "AGENTS.md" in filenames:
            paths.add(Path(directory) / "AGENTS.md")
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def _instruction_scope(path: Path, repository_root: Path) -> str:
    if path.name != "AGENTS.md":
        return "PROVIDER_OR_CANONICAL"
    return "ROOT" if path.parent == repository_root else "SCOPED"


def _estimated_token_count(text: str) -> int:
    return (len(text.split()) * 13 + 9) // 10


def _frontmatter_value(text: str, field: str) -> str | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == field:
            return value.strip() or None
    return None


def _canonical_references(text: str) -> tuple[str, ...]:
    references = {
        token.strip("`[](){}.,:;\"'")
        for token in text.split()
        if "/" in token and token.strip("`[](){}.,:;\"'").endswith(".md")
    }
    return tuple(sorted(reference for reference in references if reference))


def _normalized_instruction_blocks(text: str) -> frozenset[str]:
    blocks = (
        " ".join(block.split()) for block in text.replace("\r\n", "\n").split("\n\n")
    )
    return frozenset(block for block in blocks if len(block) >= 80)


def _architecture_module_baseline(
    *,
    source_root: Path,
    source_path: Path,
    module_name: str,
    dependencies: tuple[str, ...],
    dependents: tuple[str, ...],
    fan_in: int,
    test_text_by_path: dict[str, str],
) -> ArchitectureModuleBaseline:
    relative_path = source_path.relative_to(source_root.parent).as_posix()
    line_count = len(source_path.read_text(encoding="utf-8").splitlines())
    package_name, _, leaf_name = module_name.rpartition(".")
    ownership_tokens = (
        relative_path,
        module_name,
        f"from {package_name} import {leaf_name}",
    )
    test_owners = tuple(
        path
        for path, text in test_text_by_path.items()
        if any(token in text for token in ownership_tokens)
    )
    hotspot_reasons: list[str] = []
    if line_count >= _ARCHITECTURE_HOTSPOT_LINE_THRESHOLD:
        hotspot_reasons.append("SOURCE_LINE_COUNT_THRESHOLD_EXCEEDED")
    if len(dependencies) >= _ARCHITECTURE_HOTSPOT_DEPENDENCY_THRESHOLD:
        hotspot_reasons.append("FAN_OUT_THRESHOLD_EXCEEDED")
    if fan_in >= _ARCHITECTURE_HOTSPOT_DEPENDENCY_THRESHOLD:
        hotspot_reasons.append("FAN_IN_THRESHOLD_EXCEEDED")
    return ArchitectureModuleBaseline(
        path=relative_path,
        line_count=line_count,
        internal_dependencies=dependencies,
        internal_dependents=dependents,
        fan_in=fan_in,
        test_owners=test_owners,
        hotspot_reasons=tuple(hotspot_reasons),
    )


def _source_module_name(source_root: Path, source_path: Path) -> str:
    parts = list(source_path.relative_to(source_root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _internal_imports(
    *,
    source_path: Path,
    module_name: str,
    module_names: dict[str, Path],
) -> tuple[str, ...]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_module_reference(alias.name, module_names)
                if resolved is not None and resolved != module_name:
                    dependencies.add(resolved)
        elif isinstance(node, ast.ImportFrom):
            candidates = _import_from_candidates(node, module_name)
            named_candidates = candidates[: len(node.names)]
            named_dependencies = {
                resolved
                for candidate in named_candidates
                if (resolved := _resolve_module_reference(candidate, module_names))
                is not None
                and resolved != module_name
            }
            if named_dependencies:
                dependencies.update(named_dependencies)
                continue
            for candidate in candidates[len(node.names) :]:
                resolved = _resolve_module_reference(candidate, module_names)
                if resolved is not None and resolved != module_name:
                    dependencies.add(resolved)
    return tuple(sorted(dependencies))


def _import_from_candidates(node: ast.ImportFrom, module_name: str) -> tuple[str, ...]:
    package_parts: list[str] = []
    if node.level:
        package_parts = module_name.split(".")[:-1]
        package_parts = package_parts[: len(package_parts) - node.level + 1]
    base_parts = [*package_parts, *(node.module or "").split(".")]
    base = ".".join(part for part in base_parts if part)
    candidates = [f"{base}.{alias.name}" for alias in node.names if base]
    if base:
        candidates.append(base)
    return tuple(candidates)


def _resolve_module_reference(
    candidate: str, module_names: dict[str, Path]
) -> str | None:
    if not candidate.startswith("ai4binance"):
        return None
    current = candidate
    while current:
        if current in module_names:
            return current
        current = current.rpartition(".")[0]
    return None


def _test_text_by_path(repository_root: Path) -> dict[str, str]:
    tests_root = repository_root / "tests"
    if not tests_root.is_dir():
        return {}
    return {
        test_path.relative_to(repository_root).as_posix(): test_path.read_text(
            encoding="utf-8"
        )
        for test_path in sorted(tests_root.rglob("test_*.py"))
    }


def _import_cycles(
    dependencies: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], ...]:
    """Return deterministic strongly connected import components."""
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(module_name: str) -> None:
        nonlocal index
        indices[module_name] = index
        lowlinks[module_name] = index
        index += 1
        stack.append(module_name)
        on_stack.add(module_name)
        for dependency in dependencies[module_name]:
            if dependency not in indices:
                visit(dependency)
                lowlinks[module_name] = min(lowlinks[module_name], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[module_name] = min(lowlinks[module_name], indices[dependency])
        if lowlinks[module_name] != indices[module_name]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == module_name:
                break
        if len(component) > 1:
            components.append(tuple(sorted(component)))

    for module_name in sorted(dependencies):
        if module_name not in indices:
            visit(module_name)
    return tuple(sorted(components))


def _runtime_kaizen_closure_gate(
    *,
    runtime_inventory: RuntimeInventorySnapshot,
    fast_feedback_commands: tuple[str, ...],
    full_gate_command: str,
    quality_gate_payload: dict[str, object] | None,
    governance_gate_payload: dict[str, object] | None,
    gate_evidence_blockers: tuple[str, ...],
) -> RuntimeKaizenClosureGate:
    approval_evidence = _governance_approval_evidence(governance_gate_payload)
    checks = (
        _focused_tests_closure_check(fast_feedback_commands),
        _runtime_inventory_closure_check(runtime_inventory),
        _quality_gate_closure_check(full_gate_command, quality_gate_payload),
        _governance_gate_closure_check(full_gate_command, governance_gate_payload),
        RuntimeKaizenClosureCheck(
            check_id="technical_governance_live_separation",
            status="PASS",
            evidence_ref="kaizen-quality:safety-invariants",
            proof_command=(
                ".venv\\Scripts\\python.exe -B -m pytest tests/test_kaizen_quality.py"
            ),
        ),
        _current_gate_evidence_coherence_check(gate_evidence_blockers),
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *(blocker for check in checks for blocker in check.blockers),
                *approval_evidence.blockers,
            )
        )
    )
    governance_closure_passed = checks[
        3
    ].status == "PASS" and approval_evidence.status in {"PASS", "NOT_REQUIRED"}
    return RuntimeKaizenClosureGate(
        status="READY" if not blockers else "RUNNING_WITH_BLOCKERS",
        technical_quality_status=(
            "TECHNICAL_QUALITY_PASS"
            if checks[2].status == "PASS"
            else "TECHNICAL_QUALITY_NOT_VERIFIED"
        ),
        governance_closure_status=(
            "GOVERNANCE_CLOSURE_PASS"
            if governance_closure_passed
            else "GOVERNANCE_CLOSURE_NOT_VERIFIED"
            if checks[3].status == "NOT_VERIFIED"
            else "GOVERNANCE_CLOSURE_BLOCKED"
        ),
        acceptance_status=(
            "ACCEPTANCE_READY" if not blockers else "ACCEPTANCE_BLOCKED"
        ),
        governance_approval_evidence=approval_evidence,
        checks=checks,
        blockers=blockers,
    )


def _current_gate_evidence_coherence_check(
    gate_evidence_blockers: tuple[str, ...],
) -> RuntimeKaizenClosureCheck:
    return RuntimeKaizenClosureCheck(
        check_id="current_gate_evidence_coherent",
        status="PASS" if not gate_evidence_blockers else "RUNNING_WITH_BLOCKERS",
        evidence_ref=(
            "runtime/artifacts/quality/gate/"
            "deterministic_quality_gate_latest.json;"
            "runtime/artifacts/quality/gate/governance_gate_latest.json"
        ),
        proof_command=(
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_kaizen_quality.py tests/test_auto_audit_loop.py"
        ),
        blockers=gate_evidence_blockers,
    )


def _focused_tests_closure_check(
    fast_feedback_commands: tuple[str, ...],
) -> RuntimeKaizenClosureCheck:
    joined = " ".join(fast_feedback_commands)
    blockers = tuple(
        blocker
        for expected, blocker in (
            ("tests/test_kaizen_quality.py", "FOCUSED_KAIZEN_TEST_COMMAND_MISSING"),
            (
                "tests/test_auto_audit_loop.py",
                "FOCUSED_AUTO_AUDIT_TEST_COMMAND_MISSING",
            ),
        )
        if expected not in joined
    )
    return RuntimeKaizenClosureCheck(
        check_id="focused_runtime_kaizen_tests_declared",
        status="PASS" if not blockers else "RUNNING_WITH_BLOCKERS",
        evidence_ref="kaizen-quality:fast-feedback-commands",
        proof_command=(
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_kaizen_quality.py tests/test_auto_audit_loop.py"
        ),
        blockers=blockers,
    )


def _runtime_inventory_closure_check(
    runtime_inventory: RuntimeInventorySnapshot,
) -> RuntimeKaizenClosureCheck:
    return RuntimeKaizenClosureCheck(
        check_id="runtime_inventory_classified",
        status="PASS" if not runtime_inventory.blockers else "RUNNING_WITH_BLOCKERS",
        evidence_ref="kaizen-quality:runtime-inventory",
        proof_command=(
            ".venv\\Scripts\\python.exe -B -m pytest tests/test_kaizen_quality.py"
        ),
        blockers=runtime_inventory.blockers,
    )


def _quality_gate_closure_check(
    full_gate_command: str,
    quality_gate_payload: dict[str, object] | None,
) -> RuntimeKaizenClosureCheck:
    if quality_gate_payload is None:
        return RuntimeKaizenClosureCheck(
            check_id="canonical_full_quality_gate_executed",
            status="NOT_VERIFIED",
            evidence_ref=(
                "runtime/artifacts/quality/gate/deterministic_quality_gate_latest.json"
            ),
            proof_command=full_gate_command,
            blockers=("FULL_QUALITY_GATE_EVIDENCE_NOT_ATTACHED",),
        )
    quality_status = str(quality_gate_payload.get("status", ""))
    technical_status = _quality_gate_technical_status(quality_gate_payload)
    pytest_pass_count = quality_gate_payload.get("pytest_pass_count")
    if not isinstance(pytest_pass_count, int):
        quality_evidence_gate = quality_gate_payload.get("quality_evidence_gate")
        if isinstance(quality_evidence_gate, dict):
            nested_quality_gate = quality_evidence_gate.get("quality_gate")
            if isinstance(nested_quality_gate, dict):
                pytest_pass_count = nested_quality_gate.get("pytest_pass_count")
    passed = (
        quality_status == "PASS"
        and technical_status == "TECHNICAL_QUALITY_PASS"
        and isinstance(pytest_pass_count, int)
        and pytest_pass_count > 0
    )
    blockers = () if passed else ("FULL_QUALITY_GATE_NOT_PASSING",)
    return RuntimeKaizenClosureCheck(
        check_id="canonical_full_quality_gate_executed",
        status="PASS" if passed else "RUNNING_WITH_BLOCKERS",
        evidence_ref=(
            "runtime/artifacts/quality/gate/deterministic_quality_gate_latest.json"
        ),
        proof_command=full_gate_command,
        blockers=blockers,
    )


def _governance_gate_closure_check(
    full_gate_command: str,
    governance_gate_payload: dict[str, object] | None,
) -> RuntimeKaizenClosureCheck:
    if governance_gate_payload is None:
        return RuntimeKaizenClosureCheck(
            check_id="governance_closure_verified",
            status="NOT_VERIFIED",
            evidence_ref=(
                "runtime/artifacts/quality/gate/"
                "c3_human_governance_closure_request_latest.json"
            ),
            proof_command=full_gate_command,
            blockers=("GOVERNANCE_CLOSURE_EVIDENCE_NOT_ATTACHED",),
        )
    status = str(governance_gate_payload.get("status", ""))
    approval_status = _nested_payload_status(
        governance_gate_payload,
        "approval_verification",
        default="",
    )
    resolver_status = _governance_resolver_status(governance_gate_payload)
    declared_blockers = _string_tuple(governance_gate_payload.get("blockers"))
    passed = (
        status == "PASS"
        and approval_status in {"PASS", "NOT_REQUIRED"}
        and resolver_status == "PASS"
        and not declared_blockers
    )
    blockers = (
        ()
        if passed
        else declared_blockers or ("C3_GOVERNANCE_APPROVAL_REQUIRED_OR_NOT_VERIFIED",)
    )
    return RuntimeKaizenClosureCheck(
        check_id="governance_closure_verified",
        status="PASS" if passed else "RUNNING_WITH_BLOCKERS",
        evidence_ref=(
            "runtime/artifacts/quality/gate/"
            "c3_human_governance_closure_request_latest.json"
        ),
        proof_command=full_gate_command,
        blockers=blockers,
    )


def _governance_approval_evidence(
    governance_gate_payload: dict[str, object] | None,
) -> GovernanceApprovalEvidence:
    if governance_gate_payload is None:
        return GovernanceApprovalEvidence(
            change_class="UNKNOWN",
            status="NOT_VERIFIED",
            required_approval_count=0,
            observed_approval_count=0,
            hard_veto=True,
            blockers=("GOVERNANCE_CLOSURE_EVIDENCE_NOT_ATTACHED",),
        )
    approval_payload = governance_gate_payload.get("approval_verification")
    if not isinstance(approval_payload, dict):
        return GovernanceApprovalEvidence(
            change_class=str(governance_gate_payload.get("change_class", "UNKNOWN")),
            status="NOT_VERIFIED",
            required_approval_count=0,
            observed_approval_count=0,
            hard_veto=True,
            blockers=("GOVERNANCE_APPROVAL_EVIDENCE_MALFORMED",),
        )
    change_class = str(
        approval_payload.get(
            "change_class",
            governance_gate_payload.get("change_class", "UNKNOWN"),
        )
    )
    status = str(approval_payload.get("status", "NOT_VERIFIED"))
    required_count_value = _nonnegative_int(
        approval_payload.get("required_approval_count")
    )
    observed_count_value = _nonnegative_int(
        approval_payload.get("observed_approval_count")
    )
    blockers = _string_tuple(approval_payload.get("blockers"))
    if required_count_value is None or observed_count_value is None:
        required_count = 0
        observed_count = 0
        blockers = (*blockers, "GOVERNANCE_APPROVAL_COUNT_INVALID")
    else:
        required_count = required_count_value
        observed_count = observed_count_value
    if status not in {"PASS", "NOT_REQUIRED", "NOT_VERIFIED", "RUNNING_WITH_BLOCKERS"}:
        status = "NOT_VERIFIED"
        blockers = (*blockers, "GOVERNANCE_APPROVAL_STATUS_INVALID")
    hard_veto = approval_payload.get("hard_veto")
    resolved_hard_veto = (
        hard_veto
        if isinstance(hard_veto, bool)
        else status not in {"PASS", "NOT_REQUIRED"}
    )
    if status == "PASS" and (
        resolved_hard_veto or blockers or observed_count < required_count
    ):
        status = "RUNNING_WITH_BLOCKERS"
        resolved_hard_veto = True
        blockers = (*blockers, "GOVERNANCE_APPROVAL_EVIDENCE_INCONSISTENT")
    if status == "NOT_REQUIRED" and (
        resolved_hard_veto or blockers or required_count or observed_count
    ):
        status = "NOT_VERIFIED"
        resolved_hard_veto = True
        blockers = (*blockers, "GOVERNANCE_APPROVAL_EVIDENCE_INCONSISTENT")
    if status in {"NOT_VERIFIED", "RUNNING_WITH_BLOCKERS"}:
        resolved_hard_veto = True
        if not blockers:
            blockers = ("GOVERNANCE_APPROVAL_NOT_VERIFIED",)
    return GovernanceApprovalEvidence(
        change_class=change_class or "UNKNOWN",
        status=status,
        required_approval_count=required_count,
        observed_approval_count=observed_count,
        hard_veto=resolved_hard_veto,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _nested_payload_status(
    payload: dict[str, object],
    field: str,
    *,
    default: str,
) -> str:
    nested = payload.get(field)
    if not isinstance(nested, dict):
        return default
    return str(nested.get("status", default))


def _governance_resolver_status(payload: dict[str, object]) -> str:
    """Read the canonical resolver decision with legacy status compatibility."""
    canonical_resolver = payload.get("deterministic_gate_resolver")
    if isinstance(canonical_resolver, dict):
        decision = canonical_resolver.get("decision")
        if isinstance(decision, str) and decision:
            return decision
    return _nested_payload_status(
        payload,
        "deterministic_resolver",
        default="",
    )


def _quality_gate_technical_status(payload: dict[str, object]) -> str:
    quality_evidence_gate = payload.get("quality_evidence_gate")
    if not isinstance(quality_evidence_gate, dict):
        return ""
    quality_gate = quality_evidence_gate.get("quality_gate")
    if isinstance(quality_gate, dict):
        return str(quality_gate.get("status", ""))
    return str(quality_evidence_gate.get("status", ""))


def _string_tuple(value: object = ()) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


@dataclass(frozen=True, slots=True)
class _RuntimeScanMetrics:
    file_count: int
    total_bytes: int
    oldest_modified_at: str | None
    newest_modified_at: str | None
    truncated: bool
    access_errors: tuple[str, ...]
    source_like_file_count: int
    non_markdown_report_count: int


def _runtime_inventory(repository_root: Path) -> RuntimeInventorySnapshot:
    runtime_root = repository_root / "runtime"
    classifications: list[RuntimeDirectoryClassification] = []
    warnings: list[str] = []
    for relative, profile in sorted(_RUNTIME_DIRECTORY_PROFILES.items()):
        path = repository_root / relative
        present = path.is_dir()
        expanded_scan = relative in {
            "runtime/reports",
            "runtime/artifacts/maintenance_archive",
        }
        metrics = _bounded_runtime_scan(
            path,
            repository_root,
            max_files=(
                50_000
                if relative == "runtime/reports"
                else 10_000
                if expanded_scan
                else 2_048
            ),
            max_directories=2_000 if expanded_scan else 256,
        )
        blockers: list[str] = []
        if relative == "runtime/reports" and metrics.non_markdown_report_count:
            blockers.append(
                f"RUNTIME_REPORT_PLACEMENT_DRIFT:{metrics.non_markdown_report_count}"
            )
        if relative == "runtime/data":
            blockers.extend(_runtime_data_snapshot_blockers(path, repository_root))
        if (
            relative == "runtime/dashboard"
            and present
            and not (path / "source-manifest.json").is_file()
        ):
            blockers.append("RUNTIME_DASHBOARD_PROVENANCE_MISSING")
        warnings.extend(_runtime_scan_warnings(relative, metrics))
        classifications.append(
            RuntimeDirectoryClassification(
                path=relative,
                present=present,
                role=profile.role,
                retention=profile.retention,
                privacy_classification=profile.privacy_classification,
                validation_status=(profile.validation_status if present else "MISSING"),
                retention_class=profile.retention_class,
                cleanup_candidate=profile.cleanup_candidate,
                cleanup_mode=profile.cleanup_mode,
                approval_required_for_cleanup=(profile.approval_required_for_cleanup),
                evidence_critical=profile.evidence_critical,
                observed_children=_observed_runtime_children(path, repository_root),
                scanned_file_count=metrics.file_count,
                scanned_total_bytes=metrics.total_bytes,
                oldest_modified_at=metrics.oldest_modified_at,
                newest_modified_at=metrics.newest_modified_at,
                scan_truncated=metrics.truncated,
                access_errors=metrics.access_errors,
                source_like_file_count=metrics.source_like_file_count,
                non_markdown_report_count=metrics.non_markdown_report_count,
                blockers=tuple(blockers),
            )
        )
    known_names = {
        relative.split("/", 1)[1]
        for relative in _RUNTIME_DIRECTORY_PROFILES
        if relative.startswith("runtime/")
    }
    if runtime_root.is_dir():
        for child in sorted(runtime_root.iterdir(), key=lambda item: item.name.lower()):
            if child.name in known_names:
                continue
            relative = _relative_runtime_path(child, repository_root)
            unknown_blockers = (f"RUNTIME_UNKNOWN_TOP_LEVEL_PATH:{relative}",)
            metrics = _bounded_runtime_scan(child, repository_root)
            warnings.extend(_runtime_scan_warnings(relative, metrics))
            classifications.append(
                RuntimeDirectoryClassification(
                    path=relative,
                    present=True,
                    role="unknown runtime output",
                    retention="review required before cleanup or retention decision",
                    privacy_classification=(
                        "unknown; treat as internal and local-only until classified"
                    ),
                    validation_status="UNKNOWN",
                    retention_class="REVIEW_REQUIRED",
                    cleanup_candidate=False,
                    cleanup_mode=None,
                    approval_required_for_cleanup=True,
                    evidence_critical=False,
                    observed_children=_observed_runtime_children(
                        child,
                        repository_root,
                    ),
                    scanned_file_count=metrics.file_count,
                    scanned_total_bytes=metrics.total_bytes,
                    oldest_modified_at=metrics.oldest_modified_at,
                    newest_modified_at=metrics.newest_modified_at,
                    scan_truncated=metrics.truncated,
                    access_errors=metrics.access_errors,
                    source_like_file_count=metrics.source_like_file_count,
                    non_markdown_report_count=metrics.non_markdown_report_count,
                    blockers=unknown_blockers,
                )
            )
    runtime_blockers: list[str] = [
        blocker
        for classification in classifications
        for blocker in classification.blockers
    ]
    return RuntimeInventorySnapshot(
        root="runtime",
        classifications=tuple(
            sorted(
                classifications,
                key=lambda item: (item.validation_status == "UNKNOWN", item.path),
            )
        ),
        blockers=tuple(runtime_blockers),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _bounded_runtime_scan(
    path: Path,
    repository_root: Path,
    *,
    max_files: int = 2_048,
    max_directories: int = 256,
) -> _RuntimeScanMetrics:
    if not path.is_dir():
        return _RuntimeScanMetrics(0, 0, None, None, False, (), 0, 0)
    stack = [path]
    directories = 0
    file_count = 0
    total_bytes = 0
    oldest: float | None = None
    newest: float | None = None
    truncated = False
    access_errors: list[str] = []
    source_like_file_count = 0
    non_markdown_report_count = 0
    source_suffixes = {".py", ".ps1", ".js", ".ts", ".tsx", ".html", ".css"}
    reports_root = repository_root / "runtime" / "reports"
    while stack:
        current = stack.pop()
        directories += 1
        if directories > max_directories:
            truncated = True
            break
        try:
            with os.scandir(current) as entries:
                ordered = sorted(entries, key=lambda entry: entry.name.lower())
        except OSError:
            access_errors.append(_relative_runtime_path(current, repository_root))
            continue
        for entry in ordered:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                access_errors.append(
                    _relative_runtime_path(Path(entry.path), repository_root)
                )
                continue
            file_count += 1
            total_bytes += stat.st_size
            oldest = stat.st_mtime if oldest is None else min(oldest, stat.st_mtime)
            newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
            suffix = Path(entry.name).suffix.lower()
            if suffix in source_suffixes:
                source_like_file_count += 1
            if path == reports_root and suffix != ".md":
                non_markdown_report_count += 1
            if file_count >= max_files:
                truncated = True
                stack.clear()
                break
    return _RuntimeScanMetrics(
        file_count=file_count,
        total_bytes=total_bytes,
        oldest_modified_at=_runtime_timestamp(oldest),
        newest_modified_at=_runtime_timestamp(newest),
        truncated=truncated,
        access_errors=tuple(dict.fromkeys(access_errors)),
        source_like_file_count=source_like_file_count,
        non_markdown_report_count=non_markdown_report_count,
    )


def _runtime_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _runtime_scan_warnings(
    relative: str,
    metrics: _RuntimeScanMetrics,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if metrics.truncated:
        warnings.append(f"RUNTIME_SCAN_TRUNCATED:{relative}")
    if metrics.access_errors:
        warnings.append(
            f"RUNTIME_SCAN_ACCESS_ERRORS:{relative}:{len(metrics.access_errors)}"
        )
    if metrics.truncated and metrics.total_bytes >= 256 * 1024 * 1024:
        warnings.append(
            f"RUNTIME_CAPACITY_LOWER_BOUND_ALERT:{relative}:{metrics.total_bytes}"
        )
    elif metrics.total_bytes >= 500 * 1024 * 1024:
        warnings.append(f"RUNTIME_CAPACITY_ALERT:{relative}:{metrics.total_bytes}")
    return tuple(warnings)


def _runtime_data_snapshot_blockers(
    data_root: Path,
    repository_root: Path,
) -> tuple[str, ...]:
    if not data_root.is_dir():
        return ()
    required_fields = {
        "schema_version",
        "owner",
        "purpose",
        "created_at_utc",
        "review_after_utc",
        "disposition",
        "replacement_path",
        "deletion_authorized",
    }
    blockers: list[str] = []
    for snapshot in sorted(data_root.glob("market-reset-*")):
        if not snapshot.is_dir():
            continue
        relative = _relative_runtime_path(snapshot, repository_root)
        marker = snapshot / ".ai4binance-retention.json"
        if not marker.is_file():
            blockers.append(f"RUNTIME_DATA_RESET_RETENTION_METADATA_MISSING:{relative}")
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blockers.append(f"RUNTIME_DATA_RESET_RETENTION_METADATA_INVALID:{relative}")
            continue
        if (
            not isinstance(payload, dict)
            or required_fields.difference(payload)
            or payload.get("schema_version") != "1.0"
            or not all(
                isinstance(payload.get(field), str) and payload[field].strip()
                for field in required_fields - {"deletion_authorized"}
            )
            or not isinstance(payload.get("deletion_authorized"), bool)
            or not str(payload.get("replacement_path", "")).startswith("runtime/data/")
        ):
            blockers.append(f"RUNTIME_DATA_RESET_RETENTION_METADATA_INVALID:{relative}")
    return tuple(blockers)


def _observed_runtime_children(path: Path, repository_root: Path) -> tuple[str, ...]:
    if not path.is_dir():
        return ()
    try:
        return tuple(
            _relative_runtime_path(child, repository_root)
            for child in sorted(path.iterdir(), key=lambda item: item.name.lower())[:8]
        )
    except OSError:
        return ()


def _relative_runtime_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return path.as_posix()


def _blocker_signals(
    cycles: tuple[tuple[datetime, tuple[str, ...]], ...],
) -> tuple[KaizenBlockerSignal, ...]:
    if not cycles:
        return ()
    first_seen: dict[str, datetime] = {}
    last_seen: dict[str, datetime] = {}
    counts: Counter[str] = Counter()
    for observed_at, blockers in cycles:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("kaizen blocker cycle timestamps must be timezone-aware")
        for blocker in blockers:
            normalized = blocker.strip()
            if not normalized:
                raise ValueError("kaizen blocker cycles cannot contain blanks")
            first_seen.setdefault(normalized, observed_at)
            last_seen[normalized] = observed_at
            counts[normalized] += 1
    latest_blockers = set(cycles[-1][1])
    signals = [
        KaizenBlockerSignal(
            blocker=blocker,
            first_seen_at=first,
            last_seen_at=last_seen[blocker],
            occurrences=counts[blocker],
            age_seconds=max(0, int((last_seen[blocker] - first).total_seconds())),
            state=(
                "PERSISTENT"
                if counts[blocker] > 1 and blocker in latest_blockers
                else "NEW"
                if blocker in latest_blockers
                else "RESOLVED"
            ),
            evidence_ref=_blocker_evidence_ref(blocker),
            proof_command=_blocker_proof_command(blocker),
            recommended_action_ref=f"resolve:{blocker}",
        )
        for blocker, first in first_seen.items()
    ]
    return tuple(
        sorted(
            signals,
            key=lambda signal: (
                signal.state != "PERSISTENT",
                -signal.age_seconds,
                -signal.occurrences,
                signal.blocker,
            ),
        )
    )


def _blocker_evidence_ref(blocker: str) -> str:
    normalized = blocker.casefold()
    if normalized.startswith("privacy:"):
        return "privacy-leak-guard"
    if normalized.startswith("runtime:"):
        return "system-report:runtime"
    if normalized.startswith("validation:"):
        return "continuous-assurance:validation"
    if normalized.startswith("opportunities:"):
        return "system-report:opportunities"
    if "traceability" in normalized:
        return "canonical-trace-journal"
    if "audit" in normalized:
        return "continuous-assurance:audit-contract"
    return "auto-audit-cycle"


def _blocker_proof_command(blocker: str) -> str:
    normalized = blocker.casefold()
    if normalized.startswith("privacy:"):
        return (
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_privacy_leak_guard.py tests/test_auto_audit_loop.py"
        )
    if normalized.startswith("runtime:"):
        return (
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_kaizen_quality.py tests/test_auto_audit_loop.py"
        )
    if normalized.startswith("validation:"):
        return (
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_validation_integrity.py tests/test_auto_audit_loop.py"
        )
    if "traceability" in normalized:
        return (
            ".venv\\Scripts\\python.exe -B -m pytest "
            "tests/test_kaizen_quality.py tests/test_governance_gate.py"
        )
    return (
        ".venv\\Scripts\\python.exe -B -m pytest "
        "tests/test_kaizen_quality.py tests/test_auto_audit_loop.py"
    )


def _traceability_matrix(
    inventory: EnforcementInventory | None,
    journal: CanonicalTraceJournal,
) -> tuple[tuple[KaizenTraceabilityMatrixRow, ...], tuple[str, ...]]:
    if inventory is None:
        return (), ()
    try:
        records = journal.records()
        journal_status = TraceabilityStatus.PASS
    except (OSError, ValueError):
        records = ()
        journal_status = TraceabilityStatus.RUNNING_WITH_BLOCKERS
    trace_refs = {
        ref
        for record in records
        for ref in (
            record.subject_ref,
            *record.evidence_refs,
            *record.related_refs,
            *record.governed_paths,
        )
    }
    rows: list[KaizenTraceabilityMatrixRow] = []
    blockers: list[str] = []
    for entry in inventory.consequential_entries():
        evidence_ref = f"enforcement_inventory:{entry.entrypoint_id}"
        recorded = journal_status is TraceabilityStatus.PASS and (
            entry.entrypoint_id in trace_refs or evidence_ref in trace_refs
        )
        status = "RECORDED" if recorded else "REQUIRED_NOT_RECORDED"
        if not recorded:
            blockers.append(f"KAIZEN_TRACEABILITY_GAP:{entry.entrypoint_id}")
        rows.append(
            KaizenTraceabilityMatrixRow(
                entrypoint_id=entry.entrypoint_id,
                policy_source=entry.policy_source,
                tests=entry.tests,
                evidence_ref=evidence_ref,
                canonical_trace_ref=(
                    f"canonical-trace:{entry.entrypoint_id}" if recorded else "MISSING"
                ),
                coverage_state=entry.coverage_state.value,
                traceability_status=status,
            )
        )
    return tuple(rows), tuple(blockers)


def _audit_contract_checks(
    continuous_assurance_payload: dict[str, object] | None,
) -> tuple[KaizenAuditContractCheck, ...]:
    if continuous_assurance_payload is None:
        return (
            KaizenAuditContractCheck(
                contract_id="contract:kaizen-continuous-assurance-payload",
                status="RUNNING_WITH_BLOCKERS",
                missing_fields=("continuous_assurance",),
                blockers=("KAIZEN_CONTINUOUS_ASSURANCE_PAYLOAD_MISSING",),
            ),
        )
    trust = continuous_assurance_payload.get("trust_assurance")
    if not isinstance(trust, dict):
        return (
            KaizenAuditContractCheck(
                contract_id="contract:kaizen-trust-assurance",
                status="RUNNING_WITH_BLOCKERS",
                missing_fields=("trust_assurance",),
                blockers=("KAIZEN_TRUST_ASSURANCE_MISSING",),
            ),
        )
    provenance = trust.get("provenance")
    if not isinstance(provenance, dict):
        return (
            KaizenAuditContractCheck(
                contract_id="contract:kaizen-decision-provenance",
                status="RUNNING_WITH_BLOCKERS",
                missing_fields=("provenance",),
                blockers=("KAIZEN_DECISION_PROVENANCE_MISSING",),
            ),
        )
    mapped_fields = {
        "event_type": "decision_kind",
        "subject_id": "decision_id",
        "subject_sha256": "provenance_hash",
        "record_sha256": "provenance_hash",
        "evidence_refs": "evidence_refs",
        "blockers": "blockers",
        "execution_allowed": "execution_allowed",
        "live_eligibility_status": "live_eligibility_status",
    }
    missing = tuple(
        field
        for field, payload_field in mapped_fields.items()
        if payload_field not in provenance
    )
    blockers = (
        tuple(f"KAIZEN_AUDIT_CONTRACT_FIELD_MISSING:{field}" for field in missing)
        if missing
        else ()
    )
    return (
        KaizenAuditContractCheck(
            contract_id="contract:kaizen-minimum-audit-event",
            status="PASS" if not missing else "RUNNING_WITH_BLOCKERS",
            missing_fields=missing,
            blockers=blockers,
        ),
    )


def _closure_entrypoint_order(
    inventory: EnforcementInventory | None,
) -> tuple[str, ...]:
    if inventory is None:
        return ()
    priority = {
        "governance_changes": 0,
        "approval_state_changes": 1,
        "registry_mutations": 2,
        "parameter_promotion": 3,
        "strategy_promotion": 4,
        "lesson_promotion": 5,
        "model_adaptation": 6,
        "workflow_admission": 7,
        "execution_intents": 8,
    }
    blocked = [
        entry
        for entry in inventory.consequential_entries()
        if entry.coverage_state.value == "BLOCKED"
    ]
    return tuple(
        entry.entrypoint_id
        for entry in sorted(
            blocked,
            key=lambda entry: (
                priority.get(entry.scope_family, 99),
                entry.entrypoint_id,
            ),
        )
    )


def required_audit_contract_fields() -> tuple[str, ...]:
    return _REQUIRED_AUDIT_FIELDS

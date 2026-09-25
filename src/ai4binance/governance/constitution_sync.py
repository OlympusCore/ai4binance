"""Fail-closed audits for constitution, code and quality evidence alignment."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import shutil

# Git metadata is read through shell-free argv calls.
import subprocess  # nosec B404
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ai4binance.governance_primitives import (
    is_technical_quality_pass,
    normalize_technical_quality_status,
)


class GovernanceAlignmentStatus(StrEnum):
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


class LooseCodeGapKind(StrEnum):
    CONSTITUTION_FAMILY_MISMATCH = "CONSTITUTION_FAMILY_MISMATCH"
    UNKNOWN_CHANGESET = "UNKNOWN_CHANGESET"
    SOURCE_WITHOUT_TEST_EVIDENCE = "SOURCE_WITHOUT_TEST_EVIDENCE"
    SOURCE_CHANGE_WITHOUT_TEST_DELTA = "SOURCE_CHANGE_WITHOUT_TEST_DELTA"
    GOVERNANCE_CODE_WITHOUT_COMPLIANCE = "GOVERNANCE_CODE_WITHOUT_COMPLIANCE"
    SOURCE_WITHOUT_WRITTEN_RULE = "SOURCE_WITHOUT_WRITTEN_RULE"
    DOCUMENT_WITHOUT_ELI10 = "DOCUMENT_WITHOUT_ELI10"
    QUALITY_EVIDENCE_MISSING = "QUALITY_EVIDENCE_MISSING"
    QUALITY_EVIDENCE_INCOMPLETE = "QUALITY_EVIDENCE_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class WrittenRuleExpectation:
    path: str
    required_fragments: tuple[str, ...]
    prohibited_fragments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("written rule path", self.path)
        _require_unique_nonblank("required fragments", self.required_fragments)
        _require_unique_nonblank("prohibited fragments", self.prohibited_fragments)


@dataclass(frozen=True, slots=True)
class LooseCodeFinding:
    kind: LooseCodeGapKind
    path: str
    detail: str
    severity: str = "HIGH"

    def __post_init__(self) -> None:
        _require_non_empty("loose code finding path", self.path)
        _require_non_empty("loose code finding detail", self.detail)
        if self.severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("loose code finding severity is invalid")


@dataclass(frozen=True, slots=True)
class QualityGateEvidence:
    status: str
    command: str
    pytest_pass_count: int | None
    coverage_percent: float | None
    coverage_source: str
    coverage_realism_proof_path: str
    coverage_realism_proof_sha256: str
    execution_allowed: bool
    promotion_status: str
    live_eligibility_status: str
    generated_at_utc: str | None = None
    workspace_attestation: WorkspaceAttestation | None = None
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if not is_technical_quality_pass(self.status):
            raise ValueError(
                "quality gate evidence must be TECHNICAL_QUALITY_PASS or the "
                "legacy QUALITY_GATE_GREEN alias"
            )
        object.__setattr__(
            self, "status", normalize_technical_quality_status(self.status)
        )
        _require_non_empty("quality gate command", self.command)
        _require_non_empty("quality gate coverage source", self.coverage_source)
        if self.pytest_pass_count is None or self.pytest_pass_count <= 0:
            raise ValueError("quality gate evidence requires pytest_pass_count")
        if self.coverage_percent is None or not 0.0 <= self.coverage_percent <= 100.0:
            raise ValueError("quality gate evidence requires honest coverage_percent")
        if (
            _normalize_path(self.coverage_realism_proof_path)
            != "runtime/artifacts/quality/gate/coverage_summary.md"
        ):
            raise ValueError("quality gate evidence requires governed markdown proof")
        if len(self.coverage_realism_proof_sha256) != 64 or any(
            char not in "0123456789abcdef"
            for char in self.coverage_realism_proof_sha256
        ):
            raise ValueError("quality gate evidence requires markdown proof hash")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("quality gate evidence cannot authorize execution")
        if self.generated_at_utc is not None and not self.generated_at_utc.strip():
            raise ValueError("quality gate evidence generated_at_utc cannot be blank")
        if self.artifact_sha256 is not None:
            _require_sha256(
                "quality gate evidence artifact_sha256", self.artifact_sha256
            )


@dataclass(frozen=True, slots=True)
class WorkspaceAttestation:
    repository_root: Path
    repository_tree_sha256: str
    git_commit: str
    change_set_sha256: str

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("workspace attestation repository_root must be absolute")
        _require_sha256(
            "workspace attestation repository_tree_sha256",
            self.repository_tree_sha256,
        )
        _require_non_empty("workspace attestation git_commit", self.git_commit)
        _require_sha256(
            "workspace attestation change_set_sha256",
            self.change_set_sha256,
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "repository_root": str(self.repository_root),
            "repository_tree_sha256": self.repository_tree_sha256,
            "git_commit": self.git_commit,
            "change_set_sha256": self.change_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class GovernanceAlignmentAuditReport:
    status: GovernanceAlignmentStatus
    repository_root: Path
    changed_paths: tuple[str, ...]
    findings: tuple[LooseCodeFinding, ...]
    quality_gate: QualityGateEvidence | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("repository root must be absolute")
        _require_unique_nonblank("changed paths", self.changed_paths)
        _require_unique_nonblank("alignment blockers", self.blockers)
        if self.status is GovernanceAlignmentStatus.PASS and self.findings:
            raise ValueError("passing alignment audit cannot contain findings")
        if self.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS and (
            not self.findings
        ):
            raise ValueError("blocked alignment audit requires findings")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("alignment audit cannot authorize execution")

    @property
    def coverage_percent(self) -> float | None:
        if self.quality_gate is None:
            return None
        return self.quality_gate.coverage_percent

    @property
    def pytest_pass_count(self) -> int | None:
        if self.quality_gate is None:
            return None
        return self.quality_gate.pytest_pass_count

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "repository_root": str(self.repository_root),
            "changed_paths": list(self.changed_paths),
            "findings": [
                {
                    "kind": finding.kind.value,
                    "path": finding.path,
                    "detail": finding.detail,
                    "severity": finding.severity,
                }
                for finding in self.findings
            ],
            "pytest_pass_count": self.pytest_pass_count,
            "coverage_percent": self.coverage_percent,
            "coverage_source": (
                None if self.quality_gate is None else self.quality_gate.coverage_source
            ),
            "coverage_realism_proof_path": (
                None
                if self.quality_gate is None
                else self.quality_gate.coverage_realism_proof_path
            ),
            "coverage_realism_proof_sha256": (
                None
                if self.quality_gate is None
                else self.quality_gate.coverage_realism_proof_sha256
            ),
            "quality_generated_at_utc": (
                None
                if self.quality_gate is None
                else self.quality_gate.generated_at_utc
            ),
            "quality_workspace_attestation": (
                None
                if self.quality_gate is None
                or self.quality_gate.workspace_attestation is None
                else self.quality_gate.workspace_attestation.to_payload()
            ),
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest")


CORE_WRITTEN_RULE_EXPECTATIONS: tuple[WrittenRuleExpectation, ...] = (
    WrittenRuleExpectation(
        path="AGENTS.md",
        required_fragments=(
            "The canonical constitution is "
            "`docs/governance/framework_core_vnext_governance.md`.",
            "`docs/governance/policy_organization_constitution_handbook.md`",
            "`docs/standards/standard_repository_file_governance.md`",
            "Codex workflows must load `docs/providers/instruction_codex_provider.md`.",
            "Claude workflows must load "
            "`docs/providers/instruction_claude_provider.md`.",
            "GOVERNANCE_CONFLICT",
            "RUNNING_WITH_BLOCKERS",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
            "Repository root describes the system. `runtime/` describes what the system",
        ),
        prohibited_fragments=("This file is an independent constitution.",),
    ),
    WrittenRuleExpectation(
        path="docs/governance/policy_organization_constitution_handbook.md",
        required_fragments=(
            "This document is the stable index for the Organization Constitution and Handbook family.",
            "This index remains the stable OEK entry point",
            "It organizes the governed policy family but does not replace the canonical constitution.",
            "The canonical constitution file is `docs/governance/framework_core_vnext_governance.md`.",
            "This document alone does not grant permission for live trading, fund transfers, production deployments, or authority expansion.",
            "Live eligibility remains `LIVE_ORDER_BLOCKED`.",
        ),
    ),
    WrittenRuleExpectation(
        path="docs/governance/framework_core_vnext_governance.md",
        required_fragments=(
            "## ELI10",
            "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
            "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
            "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
            "Risk-tiered human governance applies only when the proven change is consequential.",
            "Approval Packet",
            "scope_hash",
            "Code/constitution divergence is prohibited.",
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
        ),
        prohibited_fragments=("Behavior-changing code requires double approval.",),
    ),
    WrittenRuleExpectation(
        path="docs/standards/standard_repository_validator_governance.md",
        required_fragments=(
            "Docs are authority.",
            "Validator is enforcement.",
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "Runtime is not source-of-truth.",
            "LLM is not authority.",
            "Scores cannot hide blockers.",
            "LIVE remains blocked.",
        ),
    ),
    WrittenRuleExpectation(
        path="docs/governance/instruction_core_custom_instructions.md",
        required_fragments=(
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
            "Duplicate active source-of-truth",
            "Governed repository/file standards and machine governance contracts",
            "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
            "Human governance is consequential authority.",
            "* use BUY, SELL, HOLD, WAIT or NO_TRADE,",
            "* only A*, A and B+ quality,",
            "LIVE_ORDER_BLOCKED",
        ),
        prohibited_fragments=(
            "Behavior-changing code requires double approval.",
            "* use BUY, SELL, HOLD, WAIT_FOR_RETEST or NO_TRADE,",
            "* only A* and A quality,",
        ),
    ),
    WrittenRuleExpectation(
        path="docs/providers/instruction_codex_provider.md",
        required_fragments=(
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
    ),
    WrittenRuleExpectation(
        path="docs/compliance/registry_compliance_matrix.md",
        required_fragments=(
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
            "Quality gate is evidence.",
            "Human governance is consequential authority.",
            "LIVE remains blocked.",
            "duplicate active source-of-truth concept",
            "governed repository/file standards and machine governance contracts",
            "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
            "LIVE_ORDER_BLOCKED",
        ),
        prohibited_fragments=("dual approval",),
    ),
)


def audit_governance_alignment(
    repository_root: Path,
    *,
    changed_paths: tuple[str, ...] = (),
    quality_gate: QualityGateEvidence | None = None,
    change_scope_known: bool = True,
) -> GovernanceAlignmentAuditReport:
    """Return a report-only audit for loose code, written rules and coverage."""
    root = repository_root.resolve()
    normalized_paths = tuple(_normalize_path(path) for path in changed_paths)
    findings = list(_audit_written_rules(root))
    if not change_scope_known:
        findings.append(
            LooseCodeFinding(
                LooseCodeGapKind.UNKNOWN_CHANGESET,
                "CHANGESET",
                "Governed execution requires a deterministic change set.",
                severity="CRITICAL",
            )
        )
    findings.extend(_audit_loose_code(root, normalized_paths))
    selected_quality_gate = quality_gate or load_current_quality_gate_evidence(root)
    if selected_quality_gate is None:
        findings.append(
            LooseCodeFinding(
                LooseCodeGapKind.QUALITY_EVIDENCE_MISSING,
                "runtime/artifacts/quality/gate/latest.json",
                "Full quality gate evidence is missing.",
                severity="CRITICAL",
            )
        )
    blockers = tuple(
        dict.fromkeys(
            (
                *(f"{finding.kind.value}:{finding.path}" for finding in findings),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return GovernanceAlignmentAuditReport(
        status=(
            GovernanceAlignmentStatus.PASS
            if not findings
            else GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
        ),
        repository_root=root,
        changed_paths=normalized_paths,
        findings=tuple(findings),
        quality_gate=selected_quality_gate,
        blockers=blockers,
    )


def _audit_written_rules(root: Path) -> tuple[LooseCodeFinding, ...]:
    findings: list[LooseCodeFinding] = []
    for expectation in CORE_WRITTEN_RULE_EXPECTATIONS:
        path = root / expectation.path
        if not path.is_file():
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH,
                    expectation.path,
                    "Required constitutional document is missing.",
                    severity="CRITICAL",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        if expectation.path.startswith("docs/") and "\n## ELI10\n" not in text:
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.DOCUMENT_WITHOUT_ELI10,
                    expectation.path,
                    "Permanent governance document lacks exactly visible ELI10 block.",
                )
            )
        for fragment in expectation.required_fragments:
            if fragment not in text:
                findings.append(
                    LooseCodeFinding(
                        LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH,
                        expectation.path,
                        f"Missing canonical fragment: {fragment}",
                    )
                )
        for fragment in expectation.prohibited_fragments:
            if fragment in text:
                findings.append(
                    LooseCodeFinding(
                        LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH,
                        expectation.path,
                        f"Prohibited legacy fragment remains: {fragment}",
                        severity="HIGH",
                    )
                )
    return tuple(findings)


def _audit_loose_code(
    root: Path, changed_paths: tuple[str, ...]
) -> tuple[LooseCodeFinding, ...]:
    test_paths = tuple(path for path in changed_paths if path.startswith("tests/"))
    source_paths = tuple(
        path
        for path in changed_paths
        if path.startswith("src/ai4binance/") and path.endswith(".py")
    )
    if not source_paths:
        return ()
    docs_blob = _read_docs_blob(root)
    compliance_trace_blob = _read_compliance_trace_blob(root)
    tests_blob = _read_tests_blob(root)
    findings: list[LooseCodeFinding] = []

    for source_path in source_paths:
        module_token = _module_token(source_path)
        has_test_evidence = (
            module_token in tests_blob or Path(source_path).stem in tests_blob
        )
        has_changed_test = bool(test_paths)
        has_written_rule = source_path in docs_blob or module_token in docs_blob
        has_compliance = (
            source_path in compliance_trace_blob
            or module_token in compliance_trace_blob
        )

        if not has_test_evidence:
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.SOURCE_WITHOUT_TEST_EVIDENCE,
                    source_path,
                    "Changed source has no detectable test evidence.",
                    severity="CRITICAL",
                )
            )
        if not has_changed_test:
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.SOURCE_CHANGE_WITHOUT_TEST_DELTA,
                    source_path,
                    "Changed source set does not include a changed test file.",
                )
            )
        if source_path.startswith("src/ai4binance/governance/") and not has_compliance:
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.GOVERNANCE_CODE_WITHOUT_COMPLIANCE,
                    source_path,
                    "Governance source is not referenced by the compliance matrix.",
                    severity="CRITICAL",
                )
            )
        if not has_written_rule:
            findings.append(
                LooseCodeFinding(
                    LooseCodeGapKind.SOURCE_WITHOUT_WRITTEN_RULE,
                    source_path,
                    "Changed source is not referenced by permanent written rules.",
                )
            )
    return tuple(findings)


def _read_compliance_trace_blob(root: Path) -> str:
    """Resolve source references through documents linked by the compliance matrix."""
    compliance_path = root / "docs/compliance/registry_compliance_matrix.md"
    compliance_text = _read_text(compliance_path)
    docs_root = root / "docs"
    if not compliance_text or not docs_root.is_dir():
        return compliance_text

    documents = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(docs_root.rglob("*.md"))
        if path != compliance_path
    }
    pending = sorted(path for path in documents if path in compliance_text)
    visited: set[str] = set()
    traced_text = [compliance_text]

    while pending:
        document_path = pending.pop(0)
        if document_path in visited:
            continue
        visited.add(document_path)
        document_text = documents[document_path]
        traced_text.append(document_text)
        pending.extend(
            candidate
            for candidate in sorted(documents)
            if candidate not in visited
            and candidate not in pending
            and candidate in document_text
        )

    return "\n".join(traced_text)


def load_current_quality_gate_evidence(root: Path) -> QualityGateEvidence | None:
    """Load only a complete, current, hash-bound quality evidence envelope."""
    evidence_path = root / "runtime/artifacts/quality/gate/latest.json"
    if not evidence_path.is_file():
        return None
    try:
        raw_evidence = evidence_path.read_bytes()
    except OSError:
        return None
    try:
        payload = json.loads(raw_evidence.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != 2:
        return None
    if payload.get("verification_status") != "FULL_VERIFIED":
        return None
    if payload.get("canonical_quality_authority") is not True:
        return None
    if payload.get("full_assurance_status") != "FULL_ASSURANCE_GREEN":
        return None
    generated_at_utc = payload.get("generated_at_utc")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.strip():
        return None
    try:
        datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    proof = payload.get("coverage_realism_proof")
    if not isinstance(proof, dict):
        return None
    proof_path = _normalize_path(str(proof.get("markdown_path", "")))
    proof_hash = str(proof.get("markdown_sha256", "")).lower()
    proof_file = root / proof_path
    if not proof_file.is_file() or _sha256(proof_file) != proof_hash:
        return None
    attestation_payload = payload.get("workspace_attestation")
    if not isinstance(attestation_payload, dict):
        return None
    try:
        recorded_attestation = WorkspaceAttestation(
            repository_root=Path(str(attestation_payload.get("repository_root", ""))),
            repository_tree_sha256=str(
                attestation_payload.get("repository_tree_sha256", "")
            ).lower(),
            git_commit=str(attestation_payload.get("git_commit", "")),
            change_set_sha256=str(
                attestation_payload.get("change_set_sha256", "")
            ).lower(),
        )
    except ValueError:
        return None
    current_attestation = build_quality_gate_workspace_attestation(root)
    if not _workspace_attestations_match(current_attestation, recorded_attestation):
        return None
    try:
        return QualityGateEvidence(
            status=str(payload.get("status", "")),
            command=str(payload.get("command", "")),
            pytest_pass_count=_optional_int(payload.get("pytest_pass_count")),
            coverage_percent=_optional_float(payload.get("coverage_percent")),
            coverage_source=str(payload.get("coverage_source", "")),
            coverage_realism_proof_path=proof_path,
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=bool(payload.get("execution_allowed", True)),
            promotion_status=str(payload.get("promotion_status", "")),
            live_eligibility_status=str(payload.get("live_eligibility_status", "")),
            generated_at_utc=generated_at_utc,
            workspace_attestation=recorded_attestation,
            artifact_sha256=hashlib.sha256(raw_evidence).hexdigest(),
        )
    except ValueError:
        return None


def _load_quality_gate(root: Path) -> QualityGateEvidence | None:
    """Backward-compatible private alias for legacy internal callers."""
    return load_current_quality_gate_evidence(root)


def _read_docs_blob(root: Path) -> str:
    chunks = [
        _read_text(root / "README.md"),
        _read_text(root / "publication/README.md"),
        _read_text(root / "docs/governance/instruction_core_custom_instructions.md"),
        _read_text(root / "docs/providers/instruction_codex_provider.md"),
    ]
    docs_root = root / "docs"
    if docs_root.is_dir():
        chunks.extend(
            path.read_text(encoding="utf-8") for path in sorted(docs_root.rglob("*.md"))
        )
    return "\n".join(chunks)


def _read_tests_blob(root: Path) -> str:
    tests_root = root / "tests"
    if not tests_root.is_dir():
        return ""
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(tests_root.rglob("test_*.py"))
    )


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_token(source_path: str) -> str:
    return source_path.removeprefix("src/").removesuffix(".py").replace("/", ".")


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


_QUALITY_GATE_ATTESTATION_IGNORED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        ".codex",
        "runtime",
        "secrets",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
    }
)
_EMPTY_CHANGE_SET_SHA256 = hashlib.sha256(b"").hexdigest()


def build_quality_gate_workspace_attestation(
    repository_root: Path,
) -> WorkspaceAttestation:
    resolved_root = repository_root.resolve()
    tree_entries = tuple(_quality_gate_workspace_entries(resolved_root))
    repository_tree_sha256 = hashlib.sha256(
        "\n".join(tree_entries).encode("utf-8")
    ).hexdigest()
    return WorkspaceAttestation(
        repository_root=resolved_root,
        repository_tree_sha256=repository_tree_sha256,
        git_commit=_repository_git_commit(resolved_root),
        change_set_sha256=_quality_gate_change_set_sha256(resolved_root),
    )


def _quality_gate_workspace_entries(repository_root: Path) -> Iterable[str]:
    for current_root, dirnames, filenames in os.walk(repository_root):
        current_path = Path(current_root)
        relative_parts = (
            ()
            if current_path == repository_root
            else current_path.relative_to(repository_root).parts
        )
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _quality_gate_attestation_ignores((*relative_parts, name))
        )
        if relative_parts:
            yield f"D:{Path(*relative_parts).as_posix()}"
        for filename in sorted(filenames):
            relative_file_parts = (*relative_parts, filename)
            if _quality_gate_attestation_ignores(relative_file_parts):
                continue
            relative = Path(*relative_file_parts).as_posix()
            yield f"F:{relative}:{_sha256(repository_root / relative)}"


def _quality_gate_attestation_ignores(parts: tuple[str, ...]) -> bool:
    for part in parts:
        normalized = part.lower()
        if normalized in _QUALITY_GATE_ATTESTATION_IGNORED_PARTS:
            return True
        if normalized.startswith(".pytest-tmp"):
            return True
        if normalized == ".coverage" or normalized.startswith(".coverage."):
            return True
        if normalized.endswith((".egg-info", ".pyc", ".pyo")):
            return True
    return False


def _quality_gate_change_set_sha256(repository_root: Path) -> str:
    git_executable = _git_executable()
    if git_executable is None:
        return _EMPTY_CHANGE_SET_SHA256
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [
                git_executable,
                "-C",
                str(repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_git_discovery_environment(repository_root),
        )
    except OSError:
        return _EMPTY_CHANGE_SET_SHA256
    if completed.returncode != 0:
        return _EMPTY_CHANGE_SET_SHA256
    relevant_lines = []
    for line in completed.stdout.splitlines():
        if len(line) < 3:
            continue
        path = _parse_git_status_path(line[3:])
        if not path or not _is_quality_gate_subject_path(path):
            continue
        relevant_lines.append(f"{line[:2]} {path}")
    if not relevant_lines:
        return _EMPTY_CHANGE_SET_SHA256
    return hashlib.sha256("\n".join(sorted(relevant_lines)).encode("utf-8")).hexdigest()


def _workspace_attestations_match(
    current: WorkspaceAttestation,
    recorded: WorkspaceAttestation,
) -> bool:
    return (
        current.repository_root == recorded.repository_root
        and current.repository_tree_sha256 == recorded.repository_tree_sha256
        and current.git_commit == recorded.git_commit
        and current.change_set_sha256 == recorded.change_set_sha256
    )


def _parse_git_status_path(raw_value: str) -> str:
    value = raw_value.strip()
    if " -> " in value:
        value = value.rsplit(" -> ", maxsplit=1)[-1]
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return _normalize_path(value)


def _repository_git_commit(repository_root: Path) -> str:
    git_executable = _git_executable()
    if git_executable is None:
        return "WORKTREE_UNCOMMITTED"
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [git_executable, "-C", str(repository_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_git_discovery_environment(repository_root),
        )
    except OSError:
        return "WORKTREE_UNCOMMITTED"
    if completed.returncode != 0:
        return "WORKTREE_UNCOMMITTED"
    commit = completed.stdout.strip()
    return commit or "WORKTREE_UNCOMMITTED"


def _git_executable() -> str | None:
    return shutil.which("git")


def _git_discovery_environment(repository_root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    discovery_ceiling = str(repository_root.resolve().parent)
    existing_ceiling = environment.get("GIT_CEILING_DIRECTORIES", "").strip()
    environment["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(
        value for value in (discovery_ceiling, existing_ceiling) if value
    )
    return environment


def _is_quality_gate_subject_path(relative_path: str) -> bool:
    normalized_path = _normalize_path(relative_path)
    parts = tuple(part for part in normalized_path.split("/") if part)
    return bool(parts) and not _quality_gate_attestation_ignores(parts)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError("expected int-compatible value")
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError("expected float-compatible value")
    return float(value)

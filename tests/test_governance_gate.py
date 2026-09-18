from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance import governance_primitives as governance_primitives_module
from ai4binance.enterprise.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    WorkflowIdentity,
)
from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    TraceabilityAuditReport,
    TraceabilityStatus,
    canonical_trace_journal_path,
    canonical_trace_sha256,
)
from ai4binance.governance import constitution_sync as constitution_sync_module
from ai4binance.governance.constitution_sync import QualityGateEvidence
from ai4binance.governance.framework import ChangeApprovalClass
from ai4binance.governance.gate import (
    ApprovalVerificationStatus,
    AuthorityBaselineEvidence,
    AuthorityDocumentSnapshot,
    ConstitutionSyncGateEvidence,
    DeterministicGateDecision,
    DeterministicGateResolverEvidence,
    DeterministicQualityGateReport,
    DeterministicSubGateCheck,
    DeterministicSubGateStatus,
    GovernanceChangeSet,
    GovernanceEvidenceLifecycleStage,
    GovernanceGateReport,
    GovernanceGateStatus,
    GovernanceTestEvidence,
    QualityEvidenceGateEvidence,
    RepositoryConformanceGateEvidence,
    RepositoryHygieneGateEvidence,
    RepositoryValidatorEvidence,
    RepositoryValidatorFindingEvidence,
    SecurityScanEvidence,
    _build_repository_hygiene_gate,
    _classify_change_set,
    build_deterministic_quality_gate_report,
    build_governance_gate_report,
    load_approval_records,
    load_approval_records_with_fallback,
    load_repository_validator_evidence,
    main,
)
from tests.test_governance_constitution_sync import (
    write_core_documents,
    write_quality_evidence,
)


def _fresh_approved_at() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=5)


def _load_quality_gate(root: Path) -> QualityGateEvidence:
    payload = json.loads(
        (root / "runtime" / "artifacts" / "quality" / "gate" / "latest.json").read_text(
            encoding="utf-8-sig"
        )
    )
    proof = payload["coverage_realism_proof"]
    return QualityGateEvidence(
        status=payload["status"],
        command=payload["command"],
        pytest_pass_count=payload["pytest_pass_count"],
        coverage_percent=payload["coverage_percent"],
        coverage_source=payload["coverage_source"],
        coverage_realism_proof_path=proof["markdown_path"],
        coverage_realism_proof_sha256=proof["markdown_sha256"],
        execution_allowed=payload["execution_allowed"],
        promotion_status=payload["promotion_status"],
        live_eligibility_status=payload["live_eligibility_status"],
        generated_at_utc=payload.get("generated_at_utc"),
        workspace_attestation=(
            None
            if not isinstance(payload.get("workspace_attestation"), dict)
            else constitution_sync_module.WorkspaceAttestation(
                repository_root=Path(
                    payload["workspace_attestation"]["repository_root"]
                ),
                repository_tree_sha256=payload["workspace_attestation"][
                    "repository_tree_sha256"
                ],
                git_commit=payload["workspace_attestation"]["git_commit"],
                change_set_sha256=payload["workspace_attestation"]["change_set_sha256"],
            )
        ),
    )


def _security_scan(passed: bool = True) -> SecurityScanEvidence:
    return SecurityScanEvidence(
        check_id="BANDIT",
        command="python -m bandit -q -r src",
        passed=passed,
        failure_detail="" if passed else "Bandit security scan failed.",
    )


def _deterministic_quality_gate(
    root: Path,
    quality_gate: QualityGateEvidence,
    *,
    passed: bool = True,
    change_set: GovernanceChangeSet | None = None,
) -> DeterministicQualityGateReport:
    return build_deterministic_quality_gate_report(
        repository_root=root.resolve(),
        quality_gate=quality_gate,
        security_scan=_security_scan(passed),
        change_set=change_set,
    )


def _quality_report(
    root: Path, *, passed: bool = True, change_set: GovernanceChangeSet | None = None
) -> DeterministicQualityGateReport:
    return _deterministic_quality_gate(
        root,
        _load_quality_gate(root),
        passed=passed,
        change_set=change_set,
    )


def _change_set(root: Path, *changed_paths: str) -> GovernanceChangeSet:
    return GovernanceChangeSet(
        repository_root=root.resolve(),
        git_commit="a" * 40,
        changed_paths=changed_paths,
    )


def _approval_evidence_hash(
    quality_report: DeterministicQualityGateReport,
    provisional_report: GovernanceGateReport,
) -> str:
    payload = json.dumps(
        {
            "deterministic_governance_gate_evidence_sha256": (
                provisional_report.gate_evidence_sha256
            ),
            "deterministic_quality_gate_evidence_sha256": (
                quality_report.gate_evidence_sha256
            ),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lifecycle_definition_sha256() -> str:
    return hashlib.sha256(
        Path(governance_primitives_module.__file__).resolve().read_bytes()
    ).hexdigest()


def _write_validator_report(root: Path, *, status: str = "PASS") -> Path:
    report_path = (
        root
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "repository_validator_latest.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    blockers = [] if status == "PASS" else ["REPOSITORY_VALIDATOR_NOT_PASSING"]
    findings: list[dict[str, object]] = []
    report_path.write_text(
        json.dumps(
            {
                "status": status,
                "artifact_count": 862,
                "repository_health_score": 100 if status == "PASS" else 80,
                "blockers": blockers,
                "findings": findings,
                "recommended_actions": [],
            }
        ),
        encoding="utf-8-sig",
    )
    return report_path


def _docs_hygiene(passed: bool) -> GovernanceTestEvidence:
    return GovernanceTestEvidence(
        check_id="DOCS_HYGIENE",
        command="python -m pytest -q tests/test_docs_hygiene.py",
        selected_tests=("tests/test_docs_hygiene.py",),
        passed=passed,
        failure_detail="" if passed else "Docs hygiene subset failed.",
    )


def _artifact_hygiene(passed: bool) -> GovernanceTestEvidence:
    return GovernanceTestEvidence(
        check_id="ARTIFACT_HYGIENE",
        command="python -m pytest -q tests/test_artifact_hygiene_scripts.py",
        selected_tests=("tests/test_artifact_hygiene_scripts.py",),
        passed=passed,
        failure_detail="" if passed else "Artifact hygiene subset failed.",
    )


def _constitution_sync_tests(passed: bool) -> GovernanceTestEvidence:
    return GovernanceTestEvidence(
        check_id="CONSTITUTION_SYNC",
        command="python -m pytest -q tests/test_governance_constitution_sync.py",
        selected_tests=("tests/test_governance_constitution_sync.py",),
        passed=passed,
        failure_detail="" if passed else "Constitution sync subset failed.",
    )


def _authority_snapshot(
    canonical_path: str = "docs/governance/framework_core_vnext_governance.md",
    *,
    authority_document_id: str = "AI4B-GOV-FRM-001",
    version: str = "2.0.0",
    sha256: str = "a" * 64,
    authority_level: str = "NORMATIVE",
    source_of_truth: bool = True,
) -> AuthorityDocumentSnapshot:
    return AuthorityDocumentSnapshot(
        authority_document_id=authority_document_id,
        version=version,
        canonical_path=canonical_path,
        sha256=sha256,
        authority_level=authority_level,
        source_of_truth=source_of_truth,
    )


def _validator_finding(
    *,
    control_family: str,
    path: str,
    rule_id: str,
    severity: str = "HIGH",
    domain: str = "docs",
    blocker: bool = True,
    finding_id: str = "",
) -> RepositoryValidatorFindingEvidence:
    return RepositoryValidatorFindingEvidence(
        control_family=control_family,
        domain=domain,
        severity=severity,
        rule_id=rule_id,
        path=path,
        blocker=blocker,
        finding_id=finding_id,
    )


def _stamp_authority_frontmatter(root: Path) -> None:
    metadata_by_path = {
        "docs/governance/framework_core_vnext_governance.md": (
            "AI4B-GOV-FRM-001",
            "FRAMEWORK",
            "2.0.0",
            "Enterprise Governance",
            "NORMATIVE",
            "AUTHORITATIVE",
            "true",
        ),
        "docs/governance/instruction_core_custom_instructions.md": (
            "AI4B-GOV-INS-001",
            "INSTRUCTION",
            "2.0.0",
            "Enterprise Governance",
            "NORMATIVE",
            "AUTHORITATIVE",
            "true",
        ),
        "docs/providers/instruction_codex_provider.md": (
            "AI4B-GOV-PRV-CODEX-001",
            "PROVIDER_ADAPTER",
            "1.0.0",
            "Enterprise Governance",
            "PROVIDER_ADAPTER",
            "OPERATIONAL",
            "false",
        ),
        "docs/compliance/registry_compliance_matrix.md": (
            "AI4B-GOV-REG-001",
            "REGISTRY",
            "2.0.0",
            "Enterprise Governance",
            "NORMATIVE",
            "AUTHORITATIVE",
            "true",
        ),
    }
    for relative_path, (
        document_id,
        document_type,
        version,
        owner,
        authority_level,
        content_role,
        source_of_truth,
    ) in metadata_by_path.items():
        path = root / relative_path
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            continue
        path.write_text(
            "\n".join(
                (
                    "---",
                    f"document_id: {document_id}",
                    f"title: {path.stem}",
                    f"document_type: {document_type}",
                    f"version: {version}",
                    "status: ACTIVE",
                    f"owner: {owner}",
                    f"authority_level: {authority_level}",
                    f"content_role: {content_role}",
                    f"source_of_truth: {source_of_truth}",
                    "machine_enforceable: true",
                    "audit_required: true",
                    "classification: INTERNAL",
                    f"canonical_path: {relative_path}",
                    "---",
                    "",
                    text,
                )
            ),
            encoding="utf-8",
        )


def _write_auto_audit_traceability_artifact(
    root: Path,
    *,
    include_journal: bool,
) -> None:
    decision_id = "provenance:eaacie:traceability-test"
    evaluation_id = "policy:decision-audit"
    artifact_path = (
        root / "runtime" / "artifacts" / "auto_audit" / "auto-audit-latest.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(
            {
                "cycles": [
                    {
                        "continuous_assurance": {
                            "trust_assurance": {
                                "provenance": {"decision_id": decision_id},
                                "policy_evaluations": [
                                    {"evaluation_id": evaluation_id}
                                ],
                            }
                        }
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if not include_journal:
        return
    occurred_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    journal = CanonicalTraceJournal(canonical_trace_journal_path(root))
    journal.append(
        CanonicalTraceRecord.create(
            trace_id="trace:decision:governance-gate-test",
            trace_kind=ConsequentialTraceKind.DECISION,
            subject_ref=decision_id,
            subject_type="DECISION_PROVENANCE_RECORD",
            occurred_at=occurred_at,
            event_name="DECISION_PROVENANCE_RECORDED",
            event_status="AUDIT_ROUTE_ONLY",
            evidence_refs=("auto-audit",),
            blockers=("LIVE_ORDER_BLOCKED",),
            subject_sha256=canonical_trace_sha256({"decision_id": decision_id}),
        )
    )
    journal.append(
        CanonicalTraceRecord.create(
            trace_id="trace:policy:governance-gate-test",
            trace_kind=ConsequentialTraceKind.POLICY_EVALUATION,
            subject_ref=evaluation_id,
            subject_type="POLICY_EVALUATION_RECORD",
            occurred_at=occurred_at,
            event_name="POLICY_EVALUATION_RECORDED",
            event_status="PASSED",
            evidence_refs=("auto-audit",),
            subject_sha256=canonical_trace_sha256({"evaluation_id": evaluation_id}),
        )
    )


def test_governance_gate_passes_when_all_control_planes_pass(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path),
    )

    assert report.status is GovernanceGateStatus.PASS
    assert report.gate_id == "deterministic-governance-gate:v1"
    assert report.blockers == ()
    assert report.authority_baseline.status is DeterministicSubGateStatus.PASS
    assert len(report.authority_baseline.authority_snapshot) == 4
    assert len(report.authority_baseline.authority_snapshot_sha256) == 64
    assert report.repository_hygiene.status is DeterministicSubGateStatus.PASS
    assert report.constitution_sync.status is DeterministicSubGateStatus.PASS
    assert report.repository_conformance.status is DeterministicSubGateStatus.PASS
    assert report.quality_evidence_gate is not None
    assert report.quality_evidence_gate.status is DeterministicSubGateStatus.PASS
    assert report.deterministic_gate_resolver.decision.value == "PASS"
    assert report.repository_validator.status == "PASS"
    assert report.docs_hygiene.passed is True
    assert report.artifact_hygiene.passed is True
    assert report.constitution_sync_tests.passed is True
    assert report.alignment_status == "PASS"


def test_governance_gate_blocks_governance_module_without_bound_approval(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/gate.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "gate.py").write_text(
        "def build_gate() -> None:\n    return None\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_gate.py").write_text(
        "from ai4binance.governance import gate\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/gate.py",
        "tests/test_governance_gate.py",
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path, change_set=change_set),
        change_set=change_set,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert report.constitution_sync.status is DeterministicSubGateStatus.PASS
    assert report.alignment_findings == ()
    assert "APPROVAL_REQUIRED" in report.blockers


def test_governance_gate_blocks_repository_validator_failure(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path, status="RUNNING_WITH_BLOCKERS")
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path),
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert "REPOSITORY_VALIDATOR_NOT_PASSING" in report.blockers
    assert (
        report.repository_conformance.status
        is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    )
    assert report.deterministic_gate_resolver.decision.value == "BLOCKED"


def test_governance_gate_blocks_subset_test_failures(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(False),
        artifact_hygiene=_artifact_hygiene(False),
        constitution_sync_tests=_constitution_sync_tests(False),
        deterministic_quality_gate=_quality_report(tmp_path),
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert "DOCS_HYGIENE_TESTS_FAILED" in report.blockers
    assert "ARTIFACT_HYGIENE_TESTS_FAILED" in report.blockers
    assert "CONSTITUTION_SYNC_TESTS_FAILED" in report.blockers
    assert (
        report.repository_hygiene.status
        is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    )
    assert (
        report.constitution_sync.status
        is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    )
    assert report.deterministic_gate_resolver.decision.value == "BLOCKED"


def test_governance_gate_surfaces_alignment_findings(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    framework_path = (
        tmp_path / "docs" / "governance" / "framework_core_vnext_governance.md"
    )
    framework_path.write_text(
        framework_path.read_text(encoding="utf-8").replace(
            "Docs are authority.\n",
            "",
        ),
        encoding="utf-8",
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path),
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert any(
        blocker.startswith("CONSTITUTION_FAMILY_MISMATCH:")
        for blocker in report.blockers
    )
    assert (
        report.constitution_sync.status
        is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    )
    assert report.deterministic_gate_resolver.decision.value == "BLOCKED"
    assert report.alignment_findings


def test_governance_gate_blocks_invalid_authority_snapshot_metadata(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    framework_path = (
        tmp_path / "docs" / "governance" / "framework_core_vnext_governance.md"
    )
    framework_path.write_text(
        framework_path.read_text(encoding="utf-8").replace(
            "canonical_path: docs/governance/framework_core_vnext_governance.md",
            "canonical_path: docs/governance/renamed_framework.md",
        ),
        encoding="utf-8",
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path),
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert (
        report.authority_baseline.status
        is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    )
    assert (
        "AUTHORITY_BASELINE_CANONICAL_PATH_MISMATCH:"
        "docs/governance/framework_core_vnext_governance.md" in report.blockers
    )
    assert (
        report.deterministic_gate_resolver.decision is DeterministicGateDecision.BLOCKED
    )


def test_governance_gate_blocks_stale_quality_subject_digest(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    governance_root = tmp_path / "src" / "ai4binance" / "governance"
    governance_root.mkdir(parents=True)
    framework_path = governance_root / "framework.py"
    framework_path.write_text("class Core: ...\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)

    quality_report = _quality_report(tmp_path)
    framework_path.write_text("class Core: ...\nVALUE = 1\n", encoding="utf-8")

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert "DETERMINISTIC_QUALITY_GATE_SUBJECT_MISMATCH" in report.blockers
    assert report.quality_subject_match is False
    assert report.deterministic_gate_resolver.decision is (
        DeterministicGateDecision.BLOCKED
    )


def test_governance_gate_requires_known_change_set_for_governed_execution(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(tmp_path),
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert "UNKNOWN_CHANGESET" in report.blockers
    assert report.deterministic_gate_resolver.decision is (
        DeterministicGateDecision.BLOCKED
    )


def test_governance_gate_blocks_consequential_changes_without_bound_approval(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework_v2.py",
    )
    quality_report = _quality_report(tmp_path, change_set=change_set)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert report.change_set is not None
    assert report.change_set.change_set_sha256 == change_set.change_set_sha256
    assert quality_report.change_set is not None
    assert quality_report.subject_digest is not None
    assert report.subject_digest is not None
    assert quality_report.subject_digest.subject_id == report.subject_digest.subject_id
    assert (
        quality_report.subject_digest.change_set_sha256
        == report.subject_digest.change_set_sha256
    )
    assert quality_report.lifecycle_stage is (
        GovernanceEvidenceLifecycleStage.TECHNICAL_TRUTH_CONFIRMED
    )
    assert report.lifecycle_stage is GovernanceEvidenceLifecycleStage.BLOCKED
    assert len(quality_report.gate_evidence_sha256) == 64
    assert len(report.gate_evidence_sha256) == 64
    assert "APPROVAL_REQUIRED" in report.blockers
    approval_verification = cast(
        dict[str, object],
        report.to_payload()["approval_verification"],
    )
    assert approval_verification["change_class"] == (
        ChangeApprovalClass.C3_GOVERNED.value
    )
    assert approval_verification["status"] == (
        ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS.value
    )
    assert approval_verification["hard_veto"] is True


def test_governance_gate_hard_vetoes_missing_required_canonical_trace(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    (tmp_path / "traceability-note.txt").write_text("traceability\n", encoding="utf-8")
    _stamp_authority_frontmatter(tmp_path)
    _write_auto_audit_traceability_artifact(tmp_path, include_journal=False)
    change_set = _change_set(tmp_path, "traceability-note.txt")
    quality_report = _quality_report(tmp_path, change_set=change_set)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert report.traceability_audit is not None
    assert report.traceability_audit.status is TraceabilityStatus.RUNNING_WITH_BLOCKERS
    assert report.traceability_hard_veto is True
    assert "CANONICAL_TRACE_JOURNAL_EMPTY" in report.blockers
    assert "CANONICAL_TRACE_REQUIREMENT_MISSING" in report.blockers
    assert report.deterministic_gate_resolver.decision is (
        DeterministicGateDecision.BLOCKED
    )
    traceability_audit = cast(
        dict[str, object],
        report.to_payload()["traceability_audit"],
    )
    assert traceability_audit["requirement_count"] == 2
    assert (
        traceability_audit["status"] == TraceabilityStatus.RUNNING_WITH_BLOCKERS.value
    )


def test_classify_change_set_treats_governance_manifest_as_c3_governed(
    tmp_path: Path,
) -> None:
    change_set = _change_set(
        tmp_path,
        "config/governance/governed_document_lock_manifest.json",
    )

    assert _classify_change_set(change_set) is ChangeApprovalClass.C3_GOVERNED


def test_classify_change_set_treats_standards_documents_as_c3_governed(
    tmp_path: Path,
) -> None:
    change_set = _change_set(
        tmp_path,
        "docs/standards/standard_repository_artifact_separation_governance.md",
    )

    assert _classify_change_set(change_set) is ChangeApprovalClass.C3_GOVERNED


def test_governance_gate_passes_when_required_canonical_trace_exists(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    (tmp_path / "traceability-note.txt").write_text("traceability\n", encoding="utf-8")
    _stamp_authority_frontmatter(tmp_path)
    _write_auto_audit_traceability_artifact(tmp_path, include_journal=True)
    change_set = _change_set(tmp_path, "traceability-note.txt")
    quality_report = _quality_report(tmp_path, change_set=change_set)

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.PASS
    assert report.traceability_audit is not None
    assert report.traceability_audit.status is TraceabilityStatus.PASS
    assert report.traceability_hard_veto is True
    assert report.traceability_audit.requirement_count == 2


def test_governance_gate_verifies_bound_approval_records(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework_v2.py",
    )
    quality_report = _quality_report(tmp_path, change_set=change_set)
    provisional_report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )
    assert provisional_report.subject_digest is not None
    approved_at = _fresh_approved_at()
    approvals = (
        ApprovalRecord(
            WorkflowIdentity("wo-1", "run-1", "trace-1", approved_at),
            "approval-1",
            "reviewer-a",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="GovernanceOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
        ),
        ApprovalRecord(
            WorkflowIdentity("wo-2", "run-2", "trace-2", approved_at),
            "approval-2",
            "reviewer-b",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="ConstitutionOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
        ),
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        approval_records=approvals,
        require_change_set=True,
    )

    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert report.approval_verification.lifecycle_stage is (
        GovernanceEvidenceLifecycleStage.CONSEQUENTIAL_AUTHORITY_CONFIRMED
    )
    assert report.approval_verification.hard_veto is True
    assert report.approval_verification.observed_approval_count == 2
    assert report.approval_verification.required_approval_count == 2
    assert report.approval_verification.principal_ids == ("reviewer-a", "reviewer-b")


def test_governance_gate_blocks_duplicate_principal_ids_across_roles(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework_v2.py",
    )
    quality_report = _quality_report(tmp_path, change_set=change_set)
    provisional_report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )
    assert provisional_report.subject_digest is not None
    approved_at = _fresh_approved_at()
    approvals = (
        ApprovalRecord(
            WorkflowIdentity("wo-1", "run-1", "trace-1", approved_at),
            "approval-1",
            "reviewer-a:GovernanceOwner",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="GovernanceOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
            principal_id="reviewer-a",
        ),
        ApprovalRecord(
            WorkflowIdentity("wo-2", "run-2", "trace-2", approved_at),
            "approval-2",
            "reviewer-a:ConstitutionOwner",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="ConstitutionOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
            principal_id="reviewer-a",
        ),
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        approval_records=approvals,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert report.approval_verification is not None
    assert report.approval_verification.status is (
        ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    )
    assert "APPROVAL_PRINCIPAL_IDENTITY_COLLISION" in report.blockers


def test_governance_gate_loads_bound_approval_records_from_json_report(
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="\n".join(
            (
                "src/ai4binance/governance/gate.py",
                "src/ai4binance/governance/lean.py",
                "src/ai4binance/governance_primitives.py",
            )
        ),
    )
    write_quality_evidence(tmp_path)
    source_root = tmp_path / "src" / "ai4binance"
    (source_root / "governance").mkdir(parents=True)
    (source_root / "governance" / "gate.py").write_text(
        "class Gate: ...\n",
        encoding="utf-8",
    )
    (source_root / "governance" / "lean.py").write_text(
        "class Lean: ...\n",
        encoding="utf-8",
    )
    (source_root / "governance_primitives.py").write_text(
        "TECHNICAL_QUALITY_PRIMARY_STATUS = 'TECHNICAL_QUALITY_PASS'\n",
        encoding="utf-8",
    )
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    (tests_root / "test_governance_gate.py").write_text(
        "\n".join(
            (
                "from ai4binance.governance.gate import Gate",
                "from ai4binance.governance.lean import Lean",
                "from ai4binance import governance_primitives",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/gate.py",
        "src/ai4binance/governance/lean.py",
        "src/ai4binance/governance_primitives.py",
        "tests/test_governance_gate.py",
    )
    quality_report = _quality_report(tmp_path, change_set=change_set)
    provisional_report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )
    assert provisional_report.subject_digest is not None
    approved_at = _fresh_approved_at()
    approval_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "approval_record_latest.json"
    )
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "approval_records": [
                    {
                        "approval_id": "approval-1",
                        "approver_id": "reviewer-a",
                        "principal_id": "reviewer-a",
                        "approver_role": "GovernanceOwner",
                        "subject_ref": (
                            "runtime/artifacts/quality/gate/governance_gate_latest.json"
                        ),
                        "status": "APPROVED_FOR_IMPLEMENTATION",
                        "evidence_refs": ["artifact:governance-report"],
                        "change_class": "C3_GOVERNED",
                        "subject_sha256": provisional_report.subject_digest.subject_id,
                        "scope_hash": change_set.change_set_sha256,
                        "quality_gate_evidence_sha256": (
                            quality_report.gate_evidence_sha256
                        ),
                        "governance_gate_evidence_sha256": (
                            provisional_report.gate_evidence_sha256
                        ),
                        "evidence_hash": _approval_evidence_hash(
                            quality_report,
                            provisional_report,
                        ),
                        "authority_family_sha256": (
                            provisional_report.subject_digest.authority_family_sha256
                        ),
                        "lifecycle_definition_sha256": (_lifecycle_definition_sha256()),
                        "approved_at_utc": approved_at.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "expires_at_utc": (approved_at + timedelta(days=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                    {
                        "approval_id": "approval-2",
                        "approver_id": "reviewer-b",
                        "principal_id": "reviewer-b",
                        "approver_role": "ConstitutionOwner",
                        "subject_ref": (
                            "runtime/artifacts/quality/gate/governance_gate_latest.json"
                        ),
                        "status": "APPROVED_FOR_IMPLEMENTATION",
                        "evidence_refs": ["artifact:governance-report"],
                        "change_class": "C3_GOVERNED",
                        "subject_sha256": provisional_report.subject_digest.subject_id,
                        "scope_hash": change_set.change_set_sha256,
                        "quality_gate_evidence_sha256": (
                            quality_report.gate_evidence_sha256
                        ),
                        "governance_gate_evidence_sha256": (
                            provisional_report.gate_evidence_sha256
                        ),
                        "evidence_hash": _approval_evidence_hash(
                            quality_report,
                            provisional_report,
                        ),
                        "authority_family_sha256": (
                            provisional_report.subject_digest.authority_family_sha256
                        ),
                        "lifecycle_definition_sha256": (_lifecycle_definition_sha256()),
                        "approved_at_utc": approved_at.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "expires_at_utc": (approved_at + timedelta(days=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        approval_records=load_approval_records(approval_path),
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.PASS
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert report.approval_verification.principal_ids == ("reviewer-a", "reviewer-b")


def test_governance_gate_blocks_revoked_bound_approval_records(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    change_set = _change_set(
        tmp_path,
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework_v2.py",
    )
    quality_report = _quality_report(tmp_path, change_set=change_set)
    provisional_report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        require_change_set=True,
    )
    assert provisional_report.subject_digest is not None
    approved_at = _fresh_approved_at()
    approvals = (
        ApprovalRecord(
            WorkflowIdentity("wo-1", "run-1", "trace-1", approved_at),
            "approval-1",
            "reviewer-a",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="GovernanceOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
            revoked_at=approved_at + timedelta(minutes=30),
        ),
        ApprovalRecord(
            WorkflowIdentity("wo-2", "run-2", "trace-2", approved_at),
            "approval-2",
            "reviewer-b",
            "governance-gate",
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            ("artifact:governance-report",),
            approver_role="ConstitutionOwner",
            change_class=ChangeApprovalClass.C3_GOVERNED,
            subject_sha256=provisional_report.subject_digest.subject_id,
            scope_hash=change_set.change_set_sha256,
            quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
            governance_gate_evidence_sha256=provisional_report.gate_evidence_sha256,
            evidence_hash=_approval_evidence_hash(quality_report, provisional_report),
            authority_family_sha256=(
                provisional_report.subject_digest.authority_family_sha256
            ),
            lifecycle_definition_sha256=_lifecycle_definition_sha256(),
            approved_at=approved_at,
            expires_at=approved_at + timedelta(days=1),
        ),
    )

    report = build_governance_gate_report(
        repository_root=tmp_path,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(tmp_path)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=quality_report,
        change_set=change_set,
        approval_records=approvals,
        require_change_set=True,
    )

    assert report.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
    assert report.approval_verification is not None
    assert report.approval_verification.status is (
        ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    )
    assert "APPROVAL_REVOKED:approval-1" in report.blockers


def test_load_approval_records_with_fallback_uses_canonical_artifact_when_missing(
    tmp_path: Path,
) -> None:
    approved_at = _fresh_approved_at()
    approval_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "approval_record_latest.json"
    )
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        json.dumps(
            {
                "approval_records": [
                    {
                        "approval_id": "approval-1",
                        "approver_id": "reviewer-a",
                        "principal_id": "reviewer-a",
                        "approver_role": "GovernanceOwner",
                        "subject_ref": (
                            "runtime/artifacts/quality/gate/governance_gate_latest.json"
                        ),
                        "status": "APPROVED_FOR_IMPLEMENTATION",
                        "evidence_refs": ["artifact:governance-report"],
                        "change_class": "C2_BEHAVIORAL",
                        "subject_sha256": "a" * 64,
                        "scope_hash": "b" * 64,
                        "quality_gate_evidence_sha256": "c" * 64,
                        "governance_gate_evidence_sha256": "d" * 64,
                        "evidence_hash": "e" * 64,
                        "authority_family_sha256": "f" * 64,
                        "lifecycle_definition_sha256": "1" * 64,
                        "approved_at_utc": approved_at.isoformat().replace(
                            "+00:00",
                            "Z",
                        ),
                        "expires_at_utc": (approved_at + timedelta(days=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    approvals = load_approval_records_with_fallback(
        tmp_path,
        tmp_path / "runtime" / "artifacts" / "quality" / "gate" / "missing.json",
    )

    assert len(approvals) == 1
    assert approvals[0].approval_id == "approval-1"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "check_id": "DOCS_HYGIENE",
                "command": "python -m pytest -q tests/test_docs_hygiene.py",
                "selected_tests": ("tests/test_docs_hygiene.py",),
                "passed": True,
                "failure_detail": "should not exist",
            },
            "cannot contain failure",
        ),
        (
            {
                "check_id": "DOCS_HYGIENE",
                "command": "python -m pytest -q tests/test_docs_hygiene.py",
                "selected_tests": ("tests/test_docs_hygiene.py",),
                "passed": False,
                "execution_allowed": True,
                "failure_detail": "failed",
            },
            "cannot authorize execution",
        ),
    ],
)
def test_governance_test_evidence_rejects_invalid_fail_closed_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        GovernanceTestEvidence(**cast(Any, kwargs))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "status": "PASS",
                "report_path": (
                    "runtime/artifacts/quality/gate/repository_validator_latest.json"
                ),
                "blocker_count": -1,
                "finding_count": 0,
                "repository_health_score": 100,
                "blocker_ids": (),
            },
            "must be non-negative",
        ),
        (
            {
                "status": "PASS",
                "report_path": (
                    "runtime/artifacts/quality/gate/repository_validator_latest.json"
                ),
                "blocker_count": 0,
                "finding_count": 0,
                "repository_health_score": 101,
                "blocker_ids": (),
            },
            "must be <= 100",
        ),
        (
            {
                "status": "PASS",
                "report_path": (
                    "runtime/artifacts/quality/gate/repository_validator_latest.json"
                ),
                "blocker_count": 0,
                "finding_count": 0,
                "repository_health_score": 100,
                "blocker_ids": (),
                "promotion_status": "LIVE_APPROVED",
            },
            "cannot authorize execution",
        ),
    ],
)
def test_repository_validator_evidence_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RepositoryValidatorEvidence(**cast(Any, kwargs))


def test_repository_hygiene_gate_classifies_degraded_paths() -> None:
    validator = RepositoryValidatorEvidence(
        status="RUNNING_WITH_BLOCKERS",
        report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
        blocker_count=7,
        finding_count=0,
        repository_health_score=72,
        blocker_ids=(
            "RUNTIME_MARKDOWN_AUTHORITY_VIOLATION:runtime/report.md",
            "GENERATED_ARTIFACT_INSIDE_SRC:src/pkg/__pycache__/x.pyc",
            "UNKNOWN_TOP_LEVEL_PATH:temp-data",
            "HARDCODED_ABSOLUTE_PATH:C:/unsafe/path",
            "SCHEMA_DRIFT:contracts/foo.yaml",
            "AUTHORITY_SPLIT_BRAIN:docs/governance/framework.md",
            "PYTHON_IMPORT_DRIFT:src/ai4binance/sample.py",
        ),
        findings=(
            _validator_finding(
                control_family="DOC_HYGIENE",
                path="runtime/report.md",
                rule_id="RV-RUNTIME_MARKDOWN_AUTHORITY_VIOLATION",
                domain="runtime",
            ),
            _validator_finding(
                control_family="RUNTIME_HYGIENE",
                path="src/pkg/__pycache__/x.pyc",
                rule_id="RV-GENERATED_ARTIFACT_INSIDE_SRC",
                domain="src",
            ),
            _validator_finding(
                control_family="ARTIFACT_HYGIENE",
                path="temp-data",
                rule_id="RV-UNKNOWN_TOP_LEVEL_PATH",
                domain="temp-data",
            ),
            _validator_finding(
                control_family="CONFIG_HYGIENE",
                path="C:/unsafe/path",
                rule_id="RV-HARDCODED_ABSOLUTE_PATH",
                domain="C:",
            ),
            _validator_finding(
                control_family="SCHEMA_HYGIENE",
                path="contracts/foo.yaml",
                rule_id="RV-SCHEMA_DRIFT",
                domain="contracts",
            ),
            _validator_finding(
                control_family="POLICY_HYGIENE",
                path="docs/governance/framework.md",
                rule_id="RV-AUTHORITY_SPLIT_BRAIN",
                domain="docs",
            ),
            _validator_finding(
                control_family="SOURCE_HYGIENE",
                path="src/ai4binance/sample.py",
                rule_id="RV-PYTHON_IMPORT_DRIFT",
                domain="src",
            ),
        ),
    )

    gate = _build_repository_hygiene_gate(
        repository_validator=validator,
        docs_hygiene=_docs_hygiene(False),
        artifact_hygiene=_artifact_hygiene(False),
    )

    checks = {check.check_id: check for check in gate.checks}
    assert gate.status is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
    assert "DOCS_HYGIENE_TESTS_FAILED" in checks["DOC_HYGIENE"].blockers
    assert (
        "RV-RUNTIME_MARKDOWN_AUTHORITY_VIOLATION:runtime/report.md"
        in checks["DOC_HYGIENE"].blockers
    )
    assert "ARTIFACT_HYGIENE_TESTS_FAILED" in checks["ARTIFACT_HYGIENE"].blockers
    assert (
        "RV-GENERATED_ARTIFACT_INSIDE_SRC:src/pkg/__pycache__/x.pyc"
        in checks["RUNTIME_HYGIENE"].blockers
    )
    assert "RV-UNKNOWN_TOP_LEVEL_PATH:temp-data" in checks["ARTIFACT_HYGIENE"].blockers
    assert (
        "RV-HARDCODED_ABSOLUTE_PATH:C:/unsafe/path" in checks["CONFIG_HYGIENE"].blockers
    )
    assert "RV-SCHEMA_DRIFT:contracts/foo.yaml" in checks["SCHEMA_HYGIENE"].blockers
    assert (
        "RV-AUTHORITY_SPLIT_BRAIN:docs/governance/framework.md"
        in checks["POLICY_HYGIENE"].blockers
    )
    assert (
        "RV-PYTHON_IMPORT_DRIFT:src/ai4binance/sample.py"
        in checks["SOURCE_HYGIENE"].blockers
    )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: DeterministicSubGateCheck(
                check_id="DOC_HYGIENE",
                status=DeterministicSubGateStatus.PASS,
                blockers=("DOCS_HYGIENE_TESTS_FAILED",),
            ),
            "cannot contain blockers",
        ),
        (
            lambda: DeterministicSubGateCheck(
                check_id="DOC_HYGIENE",
                status=DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS,
                blockers=(),
            ),
            "requires blockers",
        ),
        (
            lambda: RepositoryHygieneGateEvidence(
                status=DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS,
                checks=(),
                blockers=(),
            ),
            "requires blockers",
        ),
    ],
)
def test_sub_gate_shapes_reject_invalid_status_blocker_combinations(
    factory: Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: DeterministicGateResolverEvidence(
                decision=DeterministicGateDecision.PASS,
                hard_blockers=("REPOSITORY_VALIDATOR_NOT_PASSING",),
            ),
            "cannot contain blockers",
        ),
        (
            lambda: DeterministicGateResolverEvidence(
                decision=DeterministicGateDecision.PASS_WITH_WARNINGS,
                hard_blockers=(),
                warnings=(),
            ),
            "requires warnings",
        ),
        (
            lambda: DeterministicGateResolverEvidence(
                decision=DeterministicGateDecision.BLOCKED,
                hard_blockers=(),
            ),
            "requires blockers",
        ),
    ],
)
def test_deterministic_gate_resolver_rejects_invalid_decision_shapes(
    factory: Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_authority_and_constitution_evidence_reject_duplicate_metadata() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        AuthorityBaselineEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(),
            authority_snapshot=(
                _authority_snapshot(),
                _authority_snapshot(
                    canonical_path="docs/compliance/registry_compliance_matrix.md"
                ),
            ),
            authority_snapshot_sha256="b" * 64,
        )

    with pytest.raises(ValueError, match="sha256 hex digest"):
        AuthorityDocumentSnapshot(
            authority_document_id="AI4B-GOV-FRM-001",
            version="2.0.0",
            canonical_path="docs/governance/framework_core_vnext_governance.md",
            sha256="bad",
            authority_level="NORMATIVE",
            source_of_truth=True,
        )

    with pytest.raises(ValueError, match="must be unique"):
        ConstitutionSyncGateEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(
                "CONSTITUTION_SYNC_TESTS_FAILED",
                "CONSTITUTION_SYNC_TESTS_FAILED",
            ),
            selected_tests=("tests/test_governance_constitution_sync.py",),
            command=("python -m pytest -q tests/test_governance_constitution_sync.py"),
            alignment_status="PASS",
            alignment_findings=(),
        )


def test_gate_evidence_payloads_preserve_fail_closed_defaults(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path, compliance_extra="src/ai4binance/governance/framework.py"
    )
    write_quality_evidence(tmp_path)
    quality_gate = _load_quality_gate(tmp_path)

    docs = _docs_hygiene(True)
    validator = RepositoryValidatorEvidence(
        status="PASS",
        report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
        blocker_count=0,
        finding_count=0,
        repository_health_score=100,
        blocker_ids=(),
    )
    sub_gate = DeterministicSubGateCheck(
        check_id="DOC_HYGIENE",
        status=DeterministicSubGateStatus.PASS,
        blockers=(),
    )
    hygiene = RepositoryHygieneGateEvidence(
        status=DeterministicSubGateStatus.PASS,
        checks=(sub_gate,),
        blockers=(),
    )
    authority = AuthorityBaselineEvidence(
        status=DeterministicSubGateStatus.PASS,
        blockers=(),
        authority_snapshot=(_authority_snapshot(),),
        authority_snapshot_sha256="b" * 64,
    )
    constitution = ConstitutionSyncGateEvidence(
        status=DeterministicSubGateStatus.PASS,
        blockers=(),
        selected_tests=("tests/test_governance_constitution_sync.py",),
        command=("python -m pytest -q tests/test_governance_constitution_sync.py"),
        alignment_status="PASS",
        alignment_findings=(),
    )
    conformance = RepositoryConformanceGateEvidence(
        status=DeterministicSubGateStatus.PASS,
        blockers=(),
        validator=validator,
    )
    quality_evidence = QualityEvidenceGateEvidence(
        status=DeterministicSubGateStatus.PASS,
        blockers=(),
        quality_gate=quality_gate,
    )
    resolver = DeterministicGateResolverEvidence(
        decision=DeterministicGateDecision.PASS,
        hard_blockers=(),
    )
    report = GovernanceGateReport(
        gate_id="deterministic-quality-gate:v2",
        repository_root=tmp_path.resolve(),
        status=GovernanceGateStatus.PASS,
        deterministic_quality_gate=_deterministic_quality_gate(
            tmp_path,
            quality_gate,
        ),
        authority_baseline=authority,
        repository_hygiene=hygiene,
        constitution_sync=constitution,
        repository_conformance=conformance,
        quality_evidence_gate=quality_evidence,
        deterministic_gate_resolver=resolver,
        repository_validator=validator,
        docs_hygiene=docs,
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        alignment_status="PASS",
        alignment_findings=(),
        quality_gate=quality_gate,
        blockers=(),
    )

    assert docs.to_payload()["execution_allowed"] is False
    assert validator.to_payload()["execution_allowed"] is False
    assert sub_gate.to_payload()["status"] == "PASS"
    hygiene_payload = hygiene.to_payload()
    authority_payload = authority.to_payload()
    constitution_payload = constitution.to_payload()
    conformance_payload = conformance.to_payload()
    quality_evidence_payload = quality_evidence.to_payload()
    resolver_payload = resolver.to_payload()
    report_payload = report.to_payload()

    assert (
        cast(list[dict[str, object]], hygiene_payload["checks"])[0]["check_id"]
        == "DOC_HYGIENE"
    )
    assert authority_payload["authority_sources"] == [
        "docs/governance/framework_core_vnext_governance.md"
    ]
    assert authority_payload["authority_snapshot_sha256"] == "b" * 64
    assert (
        cast(list[dict[str, object]], authority_payload["authority_snapshot"])[0][
            "authority_document_id"
        ]
        == "AI4B-GOV-FRM-001"
    )
    assert cast(str, constitution_payload["command"]).startswith("python -m pytest")
    assert cast(dict[str, object], conformance_payload["validator"])["status"] == "PASS"
    assert (
        cast(dict[str, object], quality_evidence_payload["quality_gate"])[
            "execution_allowed"
        ]
        is False
    )
    assert resolver_payload["decision"] == "PASS"
    assert (
        cast(dict[str, object], report_payload["repository_validator_gate"])["status"]
        == "PASS"
    )
    assert report_payload["quality_subject_match"] is True


def test_gate_validators_reject_blank_identity_fields(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path, compliance_extra="src/ai4binance/governance/framework.py"
    )
    write_quality_evidence(tmp_path)
    quality_gate = _load_quality_gate(tmp_path)

    with pytest.raises(ValueError, match="cannot be empty"):
        GovernanceTestEvidence(
            check_id=" ",
            command="python -m pytest -q tests/test_docs_hygiene.py",
            selected_tests=("tests/test_docs_hygiene.py",),
            passed=True,
        )

    with pytest.raises(ValueError, match="cannot contain blanks"):
        RepositoryValidatorEvidence(
            status="PASS",
            report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
            blocker_count=0,
            finding_count=0,
            repository_health_score=100,
            blocker_ids=(" ",),
        )

    with pytest.raises(ValueError, match="cannot authorize execution"):
        GovernanceGateReport(
            gate_id="deterministic-quality-gate:v2",
            repository_root=tmp_path.resolve(),
            status=GovernanceGateStatus.PASS,
            deterministic_quality_gate=_deterministic_quality_gate(
                tmp_path,
                quality_gate,
            ),
            authority_baseline=AuthorityBaselineEvidence(
                status=DeterministicSubGateStatus.PASS,
                blockers=(),
                authority_snapshot=(_authority_snapshot(),),
                authority_snapshot_sha256="b" * 64,
            ),
            repository_hygiene=RepositoryHygieneGateEvidence(
                status=DeterministicSubGateStatus.PASS,
                checks=(),
                blockers=(),
            ),
            constitution_sync=ConstitutionSyncGateEvidence(
                status=DeterministicSubGateStatus.PASS,
                blockers=(),
                selected_tests=("tests/test_governance_constitution_sync.py",),
                command=(
                    "python -m pytest -q tests/test_governance_constitution_sync.py"
                ),
                alignment_status="PASS",
                alignment_findings=(),
            ),
            repository_conformance=RepositoryConformanceGateEvidence(
                status=DeterministicSubGateStatus.PASS,
                blockers=(),
                validator=RepositoryValidatorEvidence(
                    status="PASS",
                    report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                    blocker_count=0,
                    finding_count=0,
                    repository_health_score=100,
                    blocker_ids=(),
                ),
            ),
            quality_evidence_gate=QualityEvidenceGateEvidence(
                status=DeterministicSubGateStatus.PASS,
                blockers=(),
                quality_gate=quality_gate,
            ),
            deterministic_gate_resolver=DeterministicGateResolverEvidence(
                decision=DeterministicGateDecision.PASS,
                hard_blockers=(),
            ),
            repository_validator=RepositoryValidatorEvidence(
                status="PASS",
                report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                blocker_count=0,
                finding_count=0,
                repository_health_score=100,
                blocker_ids=(),
            ),
            docs_hygiene=_docs_hygiene(True),
            artifact_hygiene=_artifact_hygiene(True),
            constitution_sync_tests=_constitution_sync_tests(True),
            alignment_status="PASS",
            alignment_findings=(),
            quality_gate=quality_gate,
            blockers=(),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda quality_gate: GovernanceGateReport(
                gate_id="deterministic-quality-gate:v2",
                repository_root=Path("relative"),
                status=GovernanceGateStatus.PASS,
                deterministic_quality_gate=_deterministic_quality_gate(
                    Path.cwd(),
                    quality_gate,
                ),
                authority_baseline=AuthorityBaselineEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    authority_snapshot=(_authority_snapshot(),),
                    authority_snapshot_sha256="b" * 64,
                ),
                repository_hygiene=RepositoryHygieneGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    checks=(),
                    blockers=(),
                ),
                constitution_sync=ConstitutionSyncGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    selected_tests=("tests/test_governance_constitution_sync.py",),
                    command=(
                        "python -m pytest -q tests/test_governance_constitution_sync.py"
                    ),
                    alignment_status="PASS",
                    alignment_findings=(),
                ),
                repository_conformance=RepositoryConformanceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    validator=RepositoryValidatorEvidence(
                        status="PASS",
                        report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                        blocker_count=0,
                        finding_count=0,
                        repository_health_score=100,
                        blocker_ids=(),
                    ),
                ),
                quality_evidence_gate=QualityEvidenceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    quality_gate=quality_gate,
                ),
                deterministic_gate_resolver=DeterministicGateResolverEvidence(
                    decision=DeterministicGateDecision.PASS,
                    hard_blockers=(),
                ),
                repository_validator=RepositoryValidatorEvidence(
                    status="PASS",
                    report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                    blocker_count=0,
                    finding_count=0,
                    repository_health_score=100,
                    blocker_ids=(),
                ),
                docs_hygiene=_docs_hygiene(True),
                artifact_hygiene=_artifact_hygiene(True),
                constitution_sync_tests=_constitution_sync_tests(True),
                alignment_status="PASS",
                alignment_findings=(),
                quality_gate=quality_gate,
                blockers=(),
            ),
            "must be absolute",
        ),
        (
            lambda quality_gate: GovernanceGateReport(
                gate_id="deterministic-quality-gate:v2",
                repository_root=Path.cwd(),
                status=GovernanceGateStatus.PASS,
                deterministic_quality_gate=_deterministic_quality_gate(
                    Path.cwd(),
                    quality_gate,
                ),
                authority_baseline=AuthorityBaselineEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    authority_snapshot=(_authority_snapshot(),),
                    authority_snapshot_sha256="b" * 64,
                ),
                repository_hygiene=RepositoryHygieneGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    checks=(),
                    blockers=(),
                ),
                constitution_sync=ConstitutionSyncGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    selected_tests=("tests/test_governance_constitution_sync.py",),
                    command=(
                        "python -m pytest -q tests/test_governance_constitution_sync.py"
                    ),
                    alignment_status="PASS",
                    alignment_findings=(),
                ),
                repository_conformance=RepositoryConformanceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    validator=RepositoryValidatorEvidence(
                        status="PASS",
                        report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                        blocker_count=0,
                        finding_count=0,
                        repository_health_score=100,
                        blocker_ids=(),
                    ),
                ),
                quality_evidence_gate=QualityEvidenceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    quality_gate=quality_gate,
                ),
                deterministic_gate_resolver=DeterministicGateResolverEvidence(
                    decision=DeterministicGateDecision.PASS,
                    hard_blockers=(),
                ),
                repository_validator=RepositoryValidatorEvidence(
                    status="PASS",
                    report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                    blocker_count=0,
                    finding_count=0,
                    repository_health_score=100,
                    blocker_ids=(),
                ),
                docs_hygiene=_docs_hygiene(True),
                artifact_hygiene=_artifact_hygiene(True),
                constitution_sync_tests=_constitution_sync_tests(True),
                alignment_status="PASS",
                alignment_findings=(),
                quality_gate=quality_gate,
                blockers=("REPOSITORY_VALIDATOR_NOT_PASSING",),
            ),
            "cannot contain blockers",
        ),
        (
            lambda quality_gate: GovernanceGateReport(
                gate_id="deterministic-quality-gate:v2",
                repository_root=Path.cwd(),
                status=GovernanceGateStatus.RUNNING_WITH_BLOCKERS,
                deterministic_quality_gate=_deterministic_quality_gate(
                    Path.cwd(),
                    quality_gate,
                ),
                authority_baseline=AuthorityBaselineEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    authority_snapshot=(_authority_snapshot(),),
                    authority_snapshot_sha256="b" * 64,
                ),
                repository_hygiene=RepositoryHygieneGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    checks=(),
                    blockers=(),
                ),
                constitution_sync=ConstitutionSyncGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    selected_tests=("tests/test_governance_constitution_sync.py",),
                    command=(
                        "python -m pytest -q tests/test_governance_constitution_sync.py"
                    ),
                    alignment_status="PASS",
                    alignment_findings=(),
                ),
                repository_conformance=RepositoryConformanceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    validator=RepositoryValidatorEvidence(
                        status="PASS",
                        report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                        blocker_count=0,
                        finding_count=0,
                        repository_health_score=100,
                        blocker_ids=(),
                    ),
                ),
                quality_evidence_gate=QualityEvidenceGateEvidence(
                    status=DeterministicSubGateStatus.PASS,
                    blockers=(),
                    quality_gate=quality_gate,
                ),
                deterministic_gate_resolver=DeterministicGateResolverEvidence(
                    decision=DeterministicGateDecision.BLOCKED,
                    hard_blockers=("REPOSITORY_VALIDATOR_NOT_PASSING",),
                ),
                repository_validator=RepositoryValidatorEvidence(
                    status="PASS",
                    report_path="runtime/artifacts/quality/gate/repository_validator_latest.json",
                    blocker_count=0,
                    finding_count=0,
                    repository_health_score=100,
                    blocker_ids=(),
                ),
                docs_hygiene=_docs_hygiene(True),
                artifact_hygiene=_artifact_hygiene(True),
                constitution_sync_tests=_constitution_sync_tests(True),
                alignment_status="PASS",
                alignment_findings=(),
                quality_gate=quality_gate,
                traceability_audit=TraceabilityAuditReport(
                    journal_path=(
                        Path.cwd()
                        / "runtime"
                        / "artifacts"
                        / "governance"
                        / "trace"
                        / "canonical_event_journal.jsonl"
                    ).resolve(),
                    status=TraceabilityStatus.PASS,
                    requirement_count=0,
                    record_count=0,
                ),
                blockers=(),
            ),
            "requires blockers",
        ),
    ],
)
def test_governance_gate_report_rejects_invalid_fail_closed_shapes(
    factory: Callable[[QualityGateEvidence], object],
    message: str,
    tmp_path: Path,
) -> None:
    write_core_documents(
        tmp_path, compliance_extra="src/ai4binance/governance/framework.py"
    )
    write_quality_evidence(tmp_path)
    quality_gate = _load_quality_gate(tmp_path)

    with pytest.raises(ValueError, match=message):
        factory(quality_gate)


def test_load_repository_validator_evidence_rejects_invalid_json_shapes(
    tmp_path: Path,
) -> None:
    list_payload = tmp_path / "validator_list.json"
    list_payload.write_text(json.dumps(["invalid"]), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_repository_validator_evidence(list_payload)

    invalid_arrays_payload = tmp_path / "validator_invalid_arrays.json"
    invalid_arrays_payload.write_text(
        json.dumps(
            {
                "status": "PASS",
                "repository_health_score": 100,
                "blockers": "not-a-list",
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be arrays"):
        load_repository_validator_evidence(invalid_arrays_payload)

    missing_structured_fields_payload = tmp_path / "validator_missing_structured.json"
    missing_structured_fields_payload.write_text(
        json.dumps(
            {
                "status": "PASS",
                "repository_health_score": 100,
                "blockers": [],
                "findings": [
                    {
                        "severity": "WARNING",
                        "path": "docs/example.md",
                        "blocker": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="control_family must be a non-empty string"):
        load_repository_validator_evidence(missing_structured_fields_payload)


def test_main_writes_blocked_gate_payload_and_lowercases_sha(tmp_path: Path) -> None:
    write_core_documents(
        tmp_path, compliance_extra="src/ai4binance/governance/framework.py"
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src" / "ai4binance" / "governance").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "governance" / "framework.py").write_text(
        "class Core: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    _stamp_authority_frontmatter(tmp_path)
    validator_path = _write_validator_report(tmp_path, status="RUNNING_WITH_BLOCKERS")
    quality_output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "deterministic_quality_gate.json"
    )
    governance_output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "deterministic_governance_gate.json"
    )
    uppercase_sha = "ABCDEF1234ABCDEF1234ABCDEF1234ABCDEF1234ABCDEF1234ABCDEF1234ABCD"
    changed_paths = (
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework_v2.py",
    )

    quality_exit_code = main(
        [
            "--mode",
            "deterministic-quality",
            "--repository-root",
            str(tmp_path),
            "--quality-gate-command",
            "powershell -File scripts/quality.ps1",
            "--pytest-pass-count",
            "3207",
            "--coverage-percent",
            "95",
            "--coverage-source",
            "runtime/tmp/coverage.json",
            "--coverage-realism-proof-path",
            "runtime/artifacts/quality/gate/coverage_summary.md",
            "--coverage-realism-proof-sha256",
            uppercase_sha,
            "--bandit-command",
            "python -m bandit -q -r src",
            "--bandit-passed",
            "true",
            "--bandit-evidence-source",
            "TEST_CAPTURE",
            "--bandit-evidence-path",
            "runtime/artifacts/quality/gate/runs/test/bandit-output.txt",
            "--bandit-evidence-sha256",
            uppercase_sha,
            "--git-commit",
            "a" * 40,
            "--changed-path",
            changed_paths[0],
            "--changed-path",
            changed_paths[1],
            "--output-json",
            str(quality_output_path),
        ]
    )
    quality_payload = json.loads(quality_output_path.read_text(encoding="utf-8"))

    exit_code = main(
        [
            "--mode",
            "governance",
            "--repository-root",
            str(tmp_path),
            "--repository-validator-report",
            str(validator_path),
            "--docs-hygiene-command",
            "python -m pytest -q tests/test_docs_hygiene.py",
            "--docs-hygiene-tests",
            "tests/test_docs_hygiene.py",
            "--docs-hygiene-passed",
            "true",
            "--docs-hygiene-evidence-source",
            "FULL_PYTEST_SUITE",
            "--docs-hygiene-evidence-path",
            "runtime/artifacts/quality/gate/runs/test/pytest-output.txt",
            "--docs-hygiene-evidence-sha256",
            uppercase_sha,
            "--artifact-hygiene-command",
            "python -m pytest -q tests/test_artifact_hygiene_scripts.py",
            "--artifact-hygiene-tests",
            "tests/test_artifact_hygiene_scripts.py",
            "--artifact-hygiene-passed",
            "true",
            "--artifact-hygiene-evidence-source",
            "FULL_PYTEST_SUITE",
            "--artifact-hygiene-evidence-path",
            "runtime/artifacts/quality/gate/runs/test/pytest-output.txt",
            "--artifact-hygiene-evidence-sha256",
            uppercase_sha,
            "--constitution-sync-command",
            "python -m pytest -q tests/test_governance_constitution_sync.py",
            "--constitution-sync-tests",
            "tests/test_governance_constitution_sync.py",
            "--constitution-sync-passed",
            "true",
            "--constitution-sync-evidence-source",
            "FULL_PYTEST_SUITE",
            "--constitution-sync-evidence-path",
            "runtime/artifacts/quality/gate/runs/test/pytest-output.txt",
            "--constitution-sync-evidence-sha256",
            uppercase_sha,
            "--deterministic-quality-gate-report",
            str(quality_output_path),
            "--git-commit",
            "a" * 40,
            "--changed-path",
            changed_paths[0],
            "--changed-path",
            changed_paths[1],
            "--output-json",
            str(governance_output_path),
        ]
    )

    payload = json.loads(governance_output_path.read_text(encoding="utf-8"))
    assert quality_exit_code == 0
    assert quality_payload["security_scan"]["evidence_sha256"] == uppercase_sha.lower()
    assert (
        quality_payload["change_set"]["change_set_sha256"]
        == (payload["change_set"]["change_set_sha256"])
    )
    assert exit_code == 2
    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert (
        payload["deterministic_quality_gate"]["gate_id"]
        == "deterministic-quality-gate:v3"
    )
    assert payload["quality_subject_match"] is True
    assert (
        payload["deterministic_quality_gate"]["subject_id"]
        == (payload["subject_digest"]["subject_id"])
    )

from __future__ import annotations

import json
import subprocess
from copy import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.enterprise.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    WorkflowIdentity,
)
from ai4binance.events.traceability import TraceabilityAuditReport, TraceabilityStatus
from ai4binance.governance import gate
from ai4binance.governance.constitution_sync import QualityGateEvidence
from ai4binance.governance.framework import ChangeApprovalClass
from ai4binance.governance.gate import (
    ApprovalVerificationEvidence,
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
    GovernanceSubjectDigest,
    GovernanceTestEvidence,
    QualityEvidenceGateEvidence,
    RepositoryConformanceGateEvidence,
    RepositoryHygieneGateEvidence,
    RepositoryValidatorEvidence,
    RepositoryValidatorFindingEvidence,
    SecurityScanEvidence,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _quality_gate() -> QualityGateEvidence:
    return QualityGateEvidence(
        status="TECHNICAL_QUALITY_PASS",
        command="python -m pytest",
        pytest_pass_count=1,
        coverage_percent=100.0,
        coverage_source="coverage.json",
        coverage_realism_proof_path=(
            "runtime/artifacts/quality/gate/coverage_summary.md"
        ),
        coverage_realism_proof_sha256=SHA_A,
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )


def _change_set(root: Path, *paths: str) -> GovernanceChangeSet:
    return GovernanceChangeSet(
        repository_root=root.resolve(),
        git_commit="a" * 40,
        changed_paths=paths,
    )


def _subject(
    root: Path,
    change_set: GovernanceChangeSet | None = None,
) -> GovernanceSubjectDigest:
    return GovernanceSubjectDigest(
        repository_root=root.resolve(),
        subject_scope="repository-governance-authority-family+implementation-state:v1",
        authority_family_sha256=SHA_A,
        repository_tree_sha256=SHA_B,
        subject_sha256=SHA_C,
        entry_count=1,
        git_commit="UNKNOWN" if change_set is None else change_set.git_commit,
        change_set_sha256="" if change_set is None else change_set.change_set_sha256,
        subject_id=SHA_C,
        changed_path_count=0 if change_set is None else len(change_set.changed_paths),
    )


def _deterministic_report(
    root: Path,
    *,
    change_set: GovernanceChangeSet | None = None,
    blocked: bool = False,
) -> DeterministicQualityGateReport:
    blockers = ("QUALITY_BLOCKED",) if blocked else ()
    return DeterministicQualityGateReport(
        gate_id="deterministic-quality-gate:v3",
        repository_root=root.resolve(),
        quality_evidence_gate=QualityEvidenceGateEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(),
            quality_gate=_quality_gate(),
        ),
        security_scan=SecurityScanEvidence(
            check_id="BANDIT",
            command="python -m bandit -q -r src",
            passed=True,
        ),
        blockers=blockers,
        status=(
            GovernanceGateStatus.RUNNING_WITH_BLOCKERS
            if blocked
            else GovernanceGateStatus.PASS
        ),
        change_set=change_set,
        subject_digest=_subject(root, change_set),
    )


def _governance_report(
    root: Path,
    *,
    change_set: GovernanceChangeSet | None = None,
    blocked: bool = False,
) -> GovernanceGateReport:
    deterministic_report = _deterministic_report(root, change_set=change_set)
    blockers = ("POLICY_BLOCKED",) if blocked else ()
    status = (
        GovernanceGateStatus.RUNNING_WITH_BLOCKERS
        if blocked
        else GovernanceGateStatus.PASS
    )
    validator = RepositoryValidatorEvidence(
        status="PASS",
        report_path="runtime/repository-validator.json",
        blocker_count=0,
        finding_count=0,
        repository_health_score=100,
        blocker_ids=(),
    )
    check = DeterministicSubGateCheck(
        check_id="REPOSITORY_VALIDATOR",
        status=DeterministicSubGateStatus.PASS,
    )
    authority_snapshot = AuthorityDocumentSnapshot(
        authority_document_id="AI4B-GOV-FRM-001",
        version="1.0.0",
        canonical_path="docs/governance/core.md",
        sha256=SHA_A,
        authority_level="CORE",
        source_of_truth=True,
    )
    test_evidence = GovernanceTestEvidence(
        check_id="DOCS_HYGIENE",
        command="python -m pytest tests/test_docs_hygiene.py",
        selected_tests=("tests/test_docs_hygiene.py",),
        passed=True,
    )
    return GovernanceGateReport(
        gate_id="deterministic-governance-gate:v1",
        repository_root=root.resolve(),
        authority_baseline=AuthorityBaselineEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(),
            authority_snapshot=(authority_snapshot,),
            authority_snapshot_sha256=SHA_B,
        ),
        repository_hygiene=RepositoryHygieneGateEvidence(
            status=DeterministicSubGateStatus.PASS,
            checks=(check,),
            blockers=(),
        ),
        constitution_sync=ConstitutionSyncGateEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(),
            selected_tests=("tests/test_governance_constitution_sync.py",),
            command="python -m pytest tests/test_governance_constitution_sync.py",
            alignment_status="PASS",
            alignment_findings=(),
        ),
        repository_conformance=RepositoryConformanceGateEvidence(
            status=DeterministicSubGateStatus.PASS,
            blockers=(),
            validator=validator,
        ),
        deterministic_gate_resolver=DeterministicGateResolverEvidence(
            decision=(
                DeterministicGateDecision.BLOCKED
                if blocked
                else DeterministicGateDecision.PASS
            ),
            hard_blockers=blockers,
        ),
        repository_validator=validator,
        docs_hygiene=test_evidence,
        artifact_hygiene=replace(test_evidence, check_id="ARTIFACT_HYGIENE"),
        constitution_sync_tests=replace(test_evidence, check_id="CONSTITUTION_SYNC"),
        alignment_status="PASS",
        alignment_findings=(),
        blockers=blockers,
        deterministic_quality_gate=deterministic_report,
        change_set=change_set,
        subject_digest=_subject(root, change_set),
        quality_subject_match=True,
        status=status,
        traceability_audit=TraceabilityAuditReport(
            journal_path=(root / "runtime" / "trace.jsonl").resolve(),
            status=TraceabilityStatus.PASS,
            requirement_count=0,
            record_count=0,
        ),
    )


def _approval_verification(
    *,
    change_class: ChangeApprovalClass = ChangeApprovalClass.C0_NON_BEHAVIORAL,
    status: ApprovalVerificationStatus = ApprovalVerificationStatus.NOT_REQUIRED,
    lifecycle_stage: GovernanceEvidenceLifecycleStage = (
        GovernanceEvidenceLifecycleStage.POLICY_ELIGIBLE
    ),
    approval_required: bool = False,
    required_approval_count: int = 0,
    observed_approval_count: int = 0,
    subject_id: str = SHA_A,
    blockers: tuple[str, ...] = (),
    hard_veto: bool = False,
    approver_ids: tuple[str, ...] = (),
) -> ApprovalVerificationEvidence:
    return ApprovalVerificationEvidence(
        change_class=change_class,
        status=status,
        lifecycle_stage=lifecycle_stage,
        approval_required=approval_required,
        required_approval_count=required_approval_count,
        observed_approval_count=observed_approval_count,
        subject_id=subject_id,
        scope_hash=SHA_A,
        deterministic_quality_gate_evidence_sha256=SHA_A,
        deterministic_governance_gate_evidence_sha256=SHA_A,
        evidence_hash=SHA_A,
        authority_family_sha256=SHA_A,
        lifecycle_definition_sha256=SHA_A,
        blockers=blockers,
        hard_veto=hard_veto,
        approver_ids=approver_ids,
    )


def _required_approval_verification(
    *,
    status: ApprovalVerificationStatus = ApprovalVerificationStatus.PASS,
    lifecycle_stage: GovernanceEvidenceLifecycleStage = (
        GovernanceEvidenceLifecycleStage.CONSEQUENTIAL_AUTHORITY_CONFIRMED
    ),
    observed_approval_count: int = 2,
    blockers: tuple[str, ...] = (),
    hard_veto: bool = True,
    approver_ids: tuple[str, ...] = (),
) -> ApprovalVerificationEvidence:
    return _approval_verification(
        change_class=ChangeApprovalClass.C3_GOVERNED,
        approval_required=True,
        required_approval_count=2,
        observed_approval_count=observed_approval_count,
        status=status,
        lifecycle_stage=lifecycle_stage,
        blockers=blockers,
        hard_veto=hard_veto,
        approver_ids=approver_ids,
    )


def _approval_record(
    quality_report: DeterministicQualityGateReport,
    governance_report: GovernanceGateReport,
) -> ApprovalRecord:
    subject = governance_report.subject_digest
    change_set = governance_report.change_set
    assert subject is not None
    assert change_set is not None
    return ApprovalRecord(
        identity=WorkflowIdentity(
            work_order_id="work-order-1",
            run_id="run-1",
            trace_id="trace-1",
            created_at=datetime.now(UTC),
        ),
        approval_id="approval-1",
        approver_id="approver-1",
        principal_id="principal-1",
        subject_ref="governance-gate",
        status=ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        evidence_refs=("governance-gate",),
        approver_role="GovernanceOwner",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256=subject.subject_id,
        scope_hash=change_set.change_set_sha256,
        quality_gate_evidence_sha256=quality_report.gate_evidence_sha256,
        governance_gate_evidence_sha256=governance_report.gate_evidence_sha256,
        evidence_hash=gate._approval_evidence_hash(
            deterministic_quality_gate=quality_report,
            governance_gate=governance_report,
        ),
        authority_family_sha256=subject.authority_family_sha256,
        lifecycle_definition_sha256=gate._lifecycle_definition_sha256(),
        approved_at=datetime.now(UTC),
    )


def _mutated_record(record: ApprovalRecord, **changes: object) -> ApprovalRecord:
    mutated = copy(record)
    for name, value in changes.items():
        object.__setattr__(mutated, name, value)
    return mutated


def test_small_evidence_contract_guards_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="cannot contain failure"):
        SecurityScanEvidence("BANDIT", "bandit", True, "unexpected")
    with pytest.raises(ValueError, match="cannot authorize execution"):
        SecurityScanEvidence("BANDIT", "bandit", True, execution_allowed=True)

    finding = RepositoryValidatorFindingEvidence(
        control_family="GOVERNANCE",
        domain="docs",
        severity="HIGH",
        rule_id="RULE",
        path="docs/core.md",
        blocker=True,
        finding_id="finding-1",
    )
    assert finding.finding_id == "finding-1"

    check = DeterministicSubGateCheck(
        check_id="CHECK",
        status=DeterministicSubGateStatus.PASS,
    )
    with pytest.raises(ValueError, match="passing repository hygiene"):
        RepositoryHygieneGateEvidence(
            DeterministicSubGateStatus.PASS,
            (check,),
            ("BLOCKER",),
        )

    with pytest.raises(ValueError, match="repository-relative posix"):
        AuthorityDocumentSnapshot("id", "1.0.0", "/absolute.md", SHA_A, "CORE", True)
    with pytest.raises(ValueError, match="semantic"):
        AuthorityDocumentSnapshot("id", "1", "core.md", SHA_A, "CORE", True)


def test_authority_baseline_contract_guards_are_fail_closed() -> None:
    snapshot = AuthorityDocumentSnapshot("id", "1.0.0", "core.md", SHA_A, "CORE", True)
    with pytest.raises(ValueError, match="lowercase sha256"):
        AuthorityBaselineEvidence(
            DeterministicSubGateStatus.PASS, (), (snapshot,), "invalid"
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        AuthorityBaselineEvidence(
            DeterministicSubGateStatus.PASS, ("BLOCKER",), (snapshot,), SHA_A
        )
    with pytest.raises(ValueError, match="requires authority snapshot"):
        AuthorityBaselineEvidence(DeterministicSubGateStatus.PASS, (), (), SHA_A)
    with pytest.raises(ValueError, match="requires blockers"):
        AuthorityBaselineEvidence(
            DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS, (), (), SHA_A
        )


def test_change_set_normalization_and_contract_guards(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        GovernanceChangeSet(Path("relative"), "a" * 40)

    derived = GovernanceChangeSet(
        tmp_path.resolve(),
        "a" * 40,
        staged_paths=("src\\a.py",),
        unstaged_paths=("src/b.py",),
        untracked_governed_paths=("docs/c.md",),
    )
    assert derived.changed_paths == ("src/a.py", "src/b.py", "docs/c.md")

    with pytest.raises(ValueError, match="must match derived paths"):
        GovernanceChangeSet(
            tmp_path.resolve(),
            "a" * 40,
            staged_paths=("src/a.py",),
            changed_paths=("src/other.py",),
        )
    with pytest.raises(ValueError, match="lowercase sha256"):
        GovernanceChangeSet(tmp_path.resolve(), "a" * 40, change_set_sha256="invalid")
    with pytest.raises(ValueError, match="does not match payload"):
        GovernanceChangeSet(tmp_path.resolve(), "a" * 40, change_set_sha256=SHA_A)


def test_subject_digest_contract_guards(tmp_path: Path) -> None:
    valid = _subject(tmp_path)
    assert valid.change_set_sha256 == gate._EMPTY_CHANGE_SET_SHA256
    with pytest.raises(ValueError, match="must be absolute"):
        replace(valid, repository_root=Path("relative"))
    with pytest.raises(ValueError, match="authority_family_sha256"):
        replace(valid, authority_family_sha256="bad")
    with pytest.raises(ValueError, match="change_set_sha256"):
        replace(valid, change_set_sha256="bad")
    with pytest.raises(ValueError, match="subject_id"):
        replace(valid, subject_id="bad")
    with pytest.raises(ValueError, match="entry_count"):
        replace(valid, entry_count=-1)
    with pytest.raises(ValueError, match="changed_path_count"):
        replace(valid, changed_path_count=-1)


def test_approval_verification_contract_guards() -> None:
    with pytest.raises(ValueError, match="sha256"):
        _approval_verification(subject_id="bad")
    with pytest.raises(ValueError, match="counts must be non-negative"):
        _approval_verification(required_approval_count=-1)
    with pytest.raises(ValueError, match="must be NOT_REQUIRED"):
        _approval_verification(status=ApprovalVerificationStatus.PASS)
    with pytest.raises(ValueError, match="cannot be a hard veto"):
        _approval_verification(hard_veto=True)
    with pytest.raises(ValueError, match="cannot require approvals"):
        _approval_verification(required_approval_count=1)
    with pytest.raises(ValueError, match="must remain policy eligible"):
        _approval_verification(lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED)

    assert _required_approval_verification().status is ApprovalVerificationStatus.PASS
    with pytest.raises(ValueError, match="must remain a hard veto"):
        _required_approval_verification(hard_veto=False)
    with pytest.raises(ValueError, match="confirm consequential authority"):
        _required_approval_verification(
            lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED
        )
    with pytest.raises(ValueError, match="enough approvals"):
        _required_approval_verification(observed_approval_count=1)
    with pytest.raises(ValueError, match="cannot contain blockers"):
        _required_approval_verification(blockers=("BLOCKER",))
    with pytest.raises(ValueError, match="requires blockers"):
        _required_approval_verification(
            status=ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS,
            lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED,
            blockers=(),
        )
    with pytest.raises(ValueError, match="must remain a hard veto"):
        _required_approval_verification(
            status=ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS,
            lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED,
            blockers=("APPROVAL_REQUIRED",),
            hard_veto=False,
        )

    blocked = _required_approval_verification(
        status=ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS,
        lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED,
        blockers=("APPROVAL_APPROVER_IDENTITY_COLLISION",),
        approver_ids=("same", "same"),
    )
    assert blocked.blockers
    with pytest.raises(ValueError, match="must be unique"):
        _required_approval_verification(
            status=ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS,
            lifecycle_stage=GovernanceEvidenceLifecycleStage.BLOCKED,
            blockers=("OTHER",),
            approver_ids=("same", "same"),
        )
    with pytest.raises(ValueError, match="cannot contain blanks"):
        _approval_verification(approver_ids=("",))


def test_approval_record_verification_rejects_each_stale_binding(
    tmp_path: Path,
) -> None:
    change_set = _change_set(tmp_path, "docs/governance/core.md")
    quality_report = _deterministic_report(tmp_path, change_set=change_set)
    governance_report = _governance_report(tmp_path, change_set=change_set)
    record = _approval_record(quality_report, governance_report)

    variants = (
        (
            _mutated_record(record, status=ApprovalStatus.PENDING),
            "APPROVAL_STATUS_NOT_APPROVED",
        ),
        (_mutated_record(record, subject_sha256=SHA_A), "APPROVAL_SUBJECT_MISMATCH"),
        (_mutated_record(record, scope_hash=SHA_A), "APPROVAL_SCOPE_MISMATCH"),
        (
            _mutated_record(record, change_class=ChangeApprovalClass.C2_BEHAVIORAL),
            "APPROVAL_CHANGE_CLASS_MISMATCH",
        ),
        (
            _mutated_record(record, quality_gate_evidence_sha256=SHA_A),
            "APPROVAL_DQG_EVIDENCE_MISMATCH",
        ),
        (
            _mutated_record(record, governance_gate_evidence_sha256=SHA_A),
            "APPROVAL_DGG_EVIDENCE_MISMATCH",
        ),
        (_mutated_record(record, evidence_hash=""), "APPROVAL_EVIDENCE_HASH_MISSING"),
        (
            _mutated_record(record, evidence_hash=SHA_A),
            "APPROVAL_EVIDENCE_HASH_MISMATCH",
        ),
        (
            _mutated_record(record, authority_family_sha256=""),
            "APPROVAL_AUTHORITY_FAMILY_MISSING",
        ),
        (
            _mutated_record(record, authority_family_sha256=SHA_B),
            "APPROVAL_AUTHORITY_FAMILY_MISMATCH",
        ),
        (
            _mutated_record(record, lifecycle_definition_sha256=""),
            "APPROVAL_LIFECYCLE_DEFINITION_MISSING",
        ),
        (
            _mutated_record(record, lifecycle_definition_sha256=SHA_A),
            "APPROVAL_LIFECYCLE_DEFINITION_MISMATCH",
        ),
        (
            _mutated_record(record, revoked_at=datetime.now(UTC)),
            "APPROVAL_REVOKED",
        ),
        (
            _mutated_record(
                record,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            "APPROVAL_EXPIRED",
        ),
    )
    for candidate, expected_blocker in variants:
        verification = gate._build_approval_verification(
            change_set=change_set,
            deterministic_quality_gate=quality_report,
            governance_gate=governance_report,
            approval_records=(candidate,),
            enforced=True,
        )
        assert any(
            blocker.startswith(expected_blocker) for blocker in verification.blockers
        )

    duplicate = _mutated_record(
        record,
        approval_id="approval-2",
        identity=replace(
            record.identity,
            work_order_id="work-order-2",
            run_id="run-2",
            trace_id="trace-2",
        ),
    )
    collisions = gate._build_approval_verification(
        change_set=change_set,
        deterministic_quality_gate=quality_report,
        governance_gate=governance_report,
        approval_records=(record, duplicate),
        enforced=True,
    )
    assert "APPROVAL_APPROVER_IDENTITY_COLLISION" in collisions.blockers
    assert "APPROVAL_PRINCIPAL_IDENTITY_COLLISION" in collisions.blockers


def test_approval_verification_requires_subject_digest(tmp_path: Path) -> None:
    change_set = _change_set(tmp_path, "docs/governance/core.md")
    quality_report = _deterministic_report(tmp_path, change_set=change_set)
    governance_report = _governance_report(tmp_path, change_set=change_set)
    object.__setattr__(governance_report, "subject_digest", None)
    with pytest.raises(ValueError, match="requires governance subject digest"):
        gate._build_approval_verification(
            change_set=change_set,
            deterministic_quality_gate=quality_report,
            governance_gate=governance_report,
            approval_records=(),
            enforced=True,
        )


def test_deterministic_report_contract_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = _deterministic_report(tmp_path)
    assert valid.to_payload()["execution_allowed"] is False
    with pytest.raises(ValueError, match="repository_root must be absolute"):
        replace(valid, repository_root=Path("relative"))
    with pytest.raises(ValueError, match="TECHNICAL_TRUTH"):
        replace(valid, authority_role="POLICY_ELIGIBILITY")
    with pytest.raises(ValueError, match="cannot contain blockers"):
        replace(valid, blockers=("BLOCKER",))
    with pytest.raises(ValueError, match="requires blockers"):
        replace(valid, status=GovernanceGateStatus.RUNNING_WITH_BLOCKERS)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(valid, execution_allowed=True)
    with pytest.raises(ValueError, match="must match repository_root"):
        replace(valid, subject_digest=_subject(tmp_path / "other"))

    change_set = _change_set(tmp_path, "src/a.py")
    bound = _deterministic_report(tmp_path, change_set=change_set)
    with pytest.raises(ValueError, match="change set must match repository_root"):
        replace(bound, change_set=_change_set(tmp_path / "other", "src/a.py"))
    with pytest.raises(ValueError, match="subject digest must match change set"):
        replace(bound, change_set=_change_set(tmp_path, "src/other.py"))
    with pytest.raises(ValueError, match="gate_evidence_sha256"):
        replace(valid, gate_evidence_sha256="invalid")

    rebuilt = replace(valid, subject_digest=None, gate_evidence_sha256="")
    assert rebuilt.subject_digest is not None
    monkeypatch.setattr(gate, "_build_governance_subject_digest", lambda *_args: None)
    with pytest.raises(ValueError, match="requires subject digest"):
        replace(valid, subject_digest=None, gate_evidence_sha256="")

    no_subject = object.__new__(DeterministicQualityGateReport)
    object.__setattr__(no_subject, "subject_digest", None)
    with pytest.raises(ValueError, match="requires subject digest"):
        no_subject.to_summary_payload()
    with pytest.raises(ValueError, match="requires subject digest"):
        no_subject._gate_evidence_payload()


def test_governance_report_contract_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = _governance_report(tmp_path)
    assert valid.to_payload()["execution_allowed"] is False
    with pytest.raises(ValueError, match="repository_root must be absolute"):
        replace(valid, repository_root=Path("relative"))
    with pytest.raises(ValueError, match="POLICY_ELIGIBILITY"):
        replace(valid, authority_role="TECHNICAL_TRUTH")
    with pytest.raises(ValueError, match="CONSEQUENTIAL_AUTHORITY"):
        replace(valid, human_governance_role="TECHNICAL_TRUTH")
    with pytest.raises(ValueError, match="requires deterministic quality gate"):
        replace(valid, deterministic_quality_gate=None)
    with pytest.raises(ValueError, match="cannot contain blockers"):
        replace(valid, blockers=("BLOCKER",))
    blocked = _governance_report(tmp_path, blocked=True)
    with pytest.raises(ValueError, match="requires blockers"):
        replace(blocked, blockers=())
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(valid, execution_allowed=True)
    with pytest.raises(ValueError, match="gate_evidence_sha256"):
        replace(valid, gate_evidence_sha256="invalid")

    change_set = _change_set(tmp_path, "src/a.py")
    bound = _governance_report(tmp_path, change_set=change_set)
    with pytest.raises(ValueError, match="subject digest must match repository_root"):
        replace(bound, subject_digest=_subject(tmp_path / "other", change_set))
    with pytest.raises(ValueError, match="change set must match repository_root"):
        replace(bound, change_set=_change_set(tmp_path / "other", "src/a.py"))
    with pytest.raises(ValueError, match="subject digest must match change set"):
        replace(bound, change_set=_change_set(tmp_path, "src/other.py"))

    monkeypatch.setattr(gate, "_build_governance_subject_digest", lambda *_args: None)
    with pytest.raises(ValueError, match="requires subject digest"):
        replace(valid, subject_digest=None, gate_evidence_sha256="")

    unresolved = object.__new__(GovernanceGateReport)
    object.__setattr__(unresolved, "status", None)
    object.__setattr__(
        unresolved,
        "deterministic_quality_gate",
        valid.deterministic_quality_gate,
    )
    object.__setattr__(unresolved, "subject_digest", valid.subject_digest)
    with pytest.raises(ValueError, match="status must be resolved"):
        unresolved._gate_evidence_payload()
    object.__setattr__(unresolved, "status", GovernanceGateStatus.PASS)
    object.__setattr__(unresolved, "deterministic_quality_gate", None)
    with pytest.raises(ValueError, match="requires deterministic quality gate"):
        unresolved._gate_evidence_payload()
    object.__setattr__(
        unresolved,
        "deterministic_quality_gate",
        valid.deterministic_quality_gate,
    )
    object.__setattr__(unresolved, "subject_digest", None)
    with pytest.raises(ValueError, match="requires subject digest"):
        unresolved._gate_evidence_payload()


def test_report_builders_cover_blocked_and_missing_evidence_routes(
    tmp_path: Path,
) -> None:
    change_set = _change_set(tmp_path, "src/a.py")
    report = gate.build_deterministic_quality_gate_report(
        repository_root=tmp_path,
        quality_gate=_quality_gate(),
        security_scan=SecurityScanEvidence(
            check_id="BANDIT",
            command="bandit",
            passed=False,
            failure_detail="failed",
        ),
        change_set=change_set,
    )
    assert report.blockers == ("SECURITY_SCAN_FAILED",)

    governance = _governance_report(tmp_path)
    with pytest.raises(ValueError, match="requires deterministic quality gate"):
        gate.build_governance_gate_report(
            repository_root=tmp_path,
            repository_validator=governance.repository_validator,
            docs_hygiene=governance.docs_hygiene,
            artifact_hygiene=governance.artifact_hygiene,
            constitution_sync_tests=governance.constitution_sync_tests,
            deterministic_quality_gate=None,
        )

    no_count = object.__new__(QualityGateEvidence)
    object.__setattr__(no_count, "pytest_pass_count", None)
    with pytest.raises(ValueError, match="requires pytest_pass_count"):
        gate._build_quality_evidence_gate(no_count)
    object.__setattr__(no_count, "pytest_pass_count", 0)
    quality_evidence = gate._build_quality_evidence_gate(no_count)
    assert quality_evidence.blockers == ("PYTEST_EVIDENCE_MISSING",)


def test_parsers_and_lineage_guards(tmp_path: Path) -> None:
    assert gate._parse_git_status_path('old.py -> "new\\path.py"') == "new/path.py"
    assert gate._parse_git_status_path("plain.py") == "plain.py"

    invalid_utf8 = tmp_path / "invalid.md"
    invalid_utf8.write_bytes(b"\xff")
    assert gate._frontmatter(invalid_utf8) is None
    no_frontmatter = tmp_path / "none.md"
    no_frontmatter.write_text("body\n", encoding="utf-8")
    assert gate._frontmatter(no_frontmatter) is None
    unfinished = tmp_path / "unfinished.md"
    unfinished.write_text("---\ntitle: Missing end\n", encoding="utf-8")
    assert gate._frontmatter(unfinished) is None
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(
        b"---\r\n  ignored: value\r\n# comment\r\nblank\r\ntitle: 'Core'\r\n---\r\n"
    )
    assert gate._frontmatter(crlf) == {"title": "Core"}

    gate._validate_optional_artifact_lineage(
        artifact_name="test", evidence_source="", evidence_path="", evidence_sha256=""
    )
    gate._validate_optional_artifact_lineage(
        artifact_name="test",
        evidence_source="source",
        evidence_path="runtime/evidence.json",
        evidence_sha256=SHA_A,
    )
    with pytest.raises(ValueError, match="complete artifact lineage"):
        gate._validate_optional_artifact_lineage(
            artifact_name="test",
            evidence_source="source",
            evidence_path="",
            evidence_sha256=SHA_A,
        )
    with pytest.raises(ValueError, match="repository-relative"):
        gate._validate_optional_artifact_lineage(
            artifact_name="test",
            evidence_source="source",
            evidence_path=str(tmp_path.resolve()),
            evidence_sha256=SHA_A,
        )
    with pytest.raises(ValueError, match="lowercase sha256"):
        gate._validate_optional_artifact_lineage(
            artifact_name="test",
            evidence_source="source",
            evidence_path="runtime/evidence.json",
            evidence_sha256="bad",
        )

    with pytest.raises(ValueError, match="is required"):
        gate._parse_approval_timestamp("approved_at", None)
    with pytest.raises(ValueError, match="ISO-8601"):
        gate._parse_approval_timestamp("approved_at", "invalid")
    with pytest.raises(ValueError, match="timezone-aware"):
        gate._parse_approval_timestamp("approved_at", "2026-01-01T00:00:00")
    assert (
        gate._parse_approval_timestamp(
            "approved_at", "2026-01-01T00:00:00Z"
        ).utcoffset()
        is not None
    )

    assert gate._metadata_bool("flag", "TRUE") is True
    assert gate._metadata_bool("flag", "false") is False
    with pytest.raises(ValueError, match="true or false"):
        gate._metadata_bool("flag", "maybe")
    with pytest.raises(ValueError, match="is required"):
        gate._require_arg(None, "argument")


def test_traceability_artifact_payload_guards() -> None:
    with pytest.raises(ValueError, match="cycles must be a list"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": {}}, report_path="audit.json"
        )
    with pytest.raises(ValueError, match="cycle payload"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": ["bad"]}, report_path="audit.json"
        )
    assert (
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": [{"continuous_assurance": None}]}, report_path="audit.json"
        )
        == ()
    )
    with pytest.raises(ValueError, match="continuous_assurance payload"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": [{"continuous_assurance": []}]}, report_path="audit.json"
        )
    with pytest.raises(ValueError, match="trust_assurance is required"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": [{"continuous_assurance": {}}]}, report_path="audit.json"
        )
    with pytest.raises(ValueError, match="provenance is required"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {"cycles": [{"continuous_assurance": {"trust_assurance": {}}}]},
            report_path="audit.json",
        )
    with pytest.raises(ValueError, match="policy_evaluations must be a list"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {
                "cycles": [
                    {
                        "continuous_assurance": {
                            "trust_assurance": {
                                "provenance": {"decision_id": "decision-1"},
                                "policy_evaluations": {},
                            }
                        }
                    }
                ]
            },
            report_path="audit.json",
        )
    with pytest.raises(ValueError, match="policy evaluation payload"):
        gate._traceability_requirements_from_auto_audit_artifact(
            {
                "cycles": [
                    {
                        "continuous_assurance": {
                            "trust_assurance": {
                                "provenance": {"decision_id": "decision-1"},
                                "policy_evaluations": ["bad"],
                            }
                        }
                    }
                ]
            },
            report_path="audit.json",
        )
    requirements = gate._traceability_requirements_from_auto_audit_artifact(
        {
            "cycles": [
                {
                    "continuous_assurance": {
                        "trust_assurance": {
                            "provenance": {"decision_id": "decision-1"},
                            "policy_evaluations": [
                                {"evaluation_id": "evaluation-1"},
                                {"evaluation_id": "evaluation-1"},
                            ],
                        }
                    }
                }
            ]
        },
        report_path="audit.json",
    )
    assert len(requirements) == 2


def test_change_class_and_subject_filters_cover_all_routes(tmp_path: Path) -> None:
    assert gate._classify_change_set(None) is ChangeApprovalClass.C0_NON_BEHAVIORAL
    assert (
        gate._classify_change_set(
            _change_set(tmp_path, "src/ai4binance/execution/live/x.py")
        )
        is ChangeApprovalClass.C4_CONSEQUENTIAL
    )
    assert (
        gate._classify_change_set(_change_set(tmp_path, "docs/governance/core.md"))
        is ChangeApprovalClass.C3_GOVERNED
    )
    assert (
        gate._classify_change_set(_change_set(tmp_path, "src/ai4binance/feature.py"))
        is ChangeApprovalClass.C2_BEHAVIORAL
    )
    assert (
        gate._classify_change_set(_change_set(tmp_path, "README.md"))
        is ChangeApprovalClass.C1_LOW_RISK
    )
    assert gate._subject_digest_ignores((".pytest-tmp-1",)) is True
    assert gate._subject_digest_ignores((".coverage",)) is True
    assert gate._subject_digest_ignores((".coverage.worker",)) is True
    assert gate._subject_digest_ignores(("src",)) is False
    assert gate._subject_digests_match(_subject(tmp_path), None) is False


def test_git_resolution_failures_and_status_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "_git_repository_root", lambda _root: None)
    assert gate.resolve_governance_change_set(tmp_path) is None

    monkeypatch.setattr(gate, "_git_repository_root", lambda root: root.resolve())
    monkeypatch.setattr(gate, "_git_executable", lambda: None)
    assert gate.resolve_governance_change_set(tmp_path) is None

    monkeypatch.setattr(gate, "_git_executable", lambda: "git")

    def raise_oserror(*_args: object, **_kwargs: object) -> None:
        raise OSError("unavailable")

    monkeypatch.setattr(subprocess, "run", raise_oserror)
    assert gate.resolve_governance_change_set(tmp_path) is None

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert gate.resolve_governance_change_set(tmp_path) is None

    status = "\n".join(
        (
            "x",
            "?? runtime/ignored.json",
            "?? docs/new.md",
            "M  src/staged.py",
            " M src/unstaged.py",
            "MM src/both.py",
        )
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=status),
    )
    monkeypatch.setattr(gate, "_repository_git_commit", lambda _root: "b" * 40)
    change_set = gate.resolve_governance_change_set(tmp_path)
    assert change_set is not None
    assert change_set.untracked_governed_paths == ("docs/new.md",)
    assert change_set.staged_paths == ("src/staged.py", "src/both.py")
    assert change_set.unstaged_paths == ("src/unstaged.py", "src/both.py")


def test_git_repository_root_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "_git_executable", lambda: None)
    assert gate._git_repository_root(tmp_path) is None

    monkeypatch.setattr(gate, "_git_executable", lambda: "git")

    def raise_oserror(*_args: object, **_kwargs: object) -> None:
        raise OSError("unavailable")

    monkeypatch.setattr(subprocess, "run", raise_oserror)
    assert gate._git_repository_root(tmp_path) is None

    for completed in (
        SimpleNamespace(returncode=1, stdout=""),
        SimpleNamespace(returncode=0, stdout=""),
    ):
        monkeypatch.setattr(
            subprocess, "run", lambda *_args, _value=completed, **_kwargs: _value
        )
        assert gate._git_repository_root(tmp_path) is None

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=str(tmp_path.resolve())
        ),
    )
    assert gate._git_repository_root(tmp_path) == tmp_path.resolve()


def test_json_loaders_reject_malformed_shapes(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        gate._load_json_report_object(path, artifact_name="report")

    path.write_text(json.dumps({"repository_health_score": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be an int"):
        gate.load_repository_validator_evidence(path)

    for payload, expected in (
        ({}, "requires quality"),
        (
            {
                "quality_evidence_gate": {},
                "security_scan": {},
                "subject_digest": {},
            },
            "requires quality gate payload",
        ),
        (
            {
                "quality_evidence_gate": {"quality_gate": {}},
                "security_scan": {},
                "subject_digest": {},
                "blockers": {},
            },
            "blockers must be an array",
        ),
        (
            {
                "quality_evidence_gate": {"quality_gate": {}},
                "security_scan": {},
                "subject_digest": {},
                "change_set": [],
            },
            "change_set must be an object",
        ),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=expected):
            gate.load_deterministic_quality_gate_report(path)

    path.write_text(json.dumps({"approval_records": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="approval_records must be an array"):
        gate.load_approval_records(path)
    path.write_text(json.dumps({"approval_records": ["bad"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="approval_records must be objects"):
        gate.load_approval_records(path)
    path.write_text(
        json.dumps(
            {
                "approval_records": [
                    {"approved_at_utc": "2026-01-01T00:00:00Z", "evidence_refs": {}}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="evidence_refs must be an array"):
        gate.load_approval_records(path)


def test_cli_helpers_cover_explicit_and_fail_closed_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = gate._cli_change_set(
        repository_root=tmp_path,
        changed_paths=["src/a.py"],
        git_commit="c" * 40,
        required=True,
    )
    assert explicit is not None
    assert explicit.git_commit == "c" * 40

    monkeypatch.setattr(gate, "resolve_governance_change_set", lambda _root: None)
    with pytest.raises(ValueError, match="requires deterministic change set"):
        gate._cli_change_set(
            repository_root=tmp_path,
            changed_paths=[],
            git_commit=None,
            required=True,
        )
    assert (
        gate._cli_change_set(
            repository_root=tmp_path,
            changed_paths=[],
            git_commit=None,
            required=False,
        )
        is None
    )

    output = tmp_path / "output.json"
    base = ["--repository-root", str(tmp_path), "--output-json", str(output)]
    with pytest.raises(ValueError, match="quality gate command is required"):
        gate.main(base)
    with pytest.raises(ValueError, match="pytest pass count is required"):
        gate.main(
            [
                *base,
                "--quality-gate-command",
                "pytest",
                "--coverage-source",
                "coverage.json",
                "--coverage-realism-proof-path",
                "runtime/artifacts/quality/gate/coverage_summary.md",
                "--coverage-realism-proof-sha256",
                SHA_A,
                "--bandit-command",
                "bandit",
            ]
        )

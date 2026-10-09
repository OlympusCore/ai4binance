"""Test-only C3 owner fixtures; no real registration or human approvals."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import yaml

from ai4binance.enterprise.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    WorkflowIdentity,
)
from ai4binance.governance.framework import ChangeApprovalClass
from ai4binance.governance.gate import (
    ApprovalVerificationStatus,
    GovernanceChangeSet,
    GovernanceGateReport,
    _approval_requirements,
    build_governance_gate_report,
    load_repository_validator_evidence,
)
from ai4binance.governance.sole_owner import (
    MODEL_CONTROL_PATHS,
    POLICY_PATH,
    SCHEMA_PATH,
    SoleOwnerConfirmation,
    SoleOwnerPolicy,
    load_sole_owner_policy,
)
from tests.test_governance_constitution_sync import (
    write_core_documents,
    write_quality_evidence,
)
from tests.test_governance_gate import (
    _approval_evidence_hash,
    _artifact_hygiene,
    _change_set,
    _constitution_sync_tests,
    _docs_hygiene,
    _lifecycle_definition_sha256,
    _quality_report,
    _stamp_authority_frontmatter,
    _write_validator_report,
)

CANDIDATE = Path(__file__).resolve().parents[1]


def _candidate_path(relative: str) -> Path:
    source = CANDIDATE / relative
    return source if source.is_file() else source.with_name(source.name + ".raw")


def _required_core_version(path: Path) -> str:
    from ai4binance.governance.repository_validator import _frontmatter

    metadata = _frontmatter(path)
    assert metadata is not None
    return metadata["version"]


PATH = "docs/standards/test_only_governed_change.md"


def test_active_owner_does_not_replay_historical_package_recognition(
    root: Path, policy: SoleOwnerPolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    def historical_package(*args: object) -> None:
        raise AssertionError("Historical package must not select permanent authority")

    monkeypatch.setattr(
        "ai4binance.governance.gate.load_package_owner_acceptance",
        historical_package,
    )
    report = _report(root, (_record(root, policy),))
    assert report.approval_verification is not None
    assert report.approval_verification.approval_profile == "SOLE_HUMAN_OWNER"
    assert report.approval_verification.required_approval_count == 1
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    _stamp_authority_frontmatter(tmp_path)
    for relative in (POLICY_PATH, SCHEMA_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_candidate_path(relative), target)
    target = tmp_path / PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Test-only governed scope.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def policy(monkeypatch: pytest.MonkeyPatch) -> SoleOwnerPolicy:
    now = datetime.now(UTC)
    selected = SoleOwnerPolicy(
        "TEST_ONLY_HUMAN",
        "TEST_ONLY_PRINCIPAL",
        frozenset({"GovernanceOwner", "ConstitutionOwner"}),
        "a" * 64,
        "b" * 64,
        now - timedelta(hours=1),
    )
    monkeypatch.setattr(
        "ai4binance.governance.gate.load_sole_owner_policy",
        lambda _root, policy_commit=None: selected,
    )
    return selected


def _report(
    root: Path,
    records: tuple[ApprovalRecord, ...] = (),
    *,
    path: str = PATH,
    quality_pass: bool = True,
    constitution_pass: bool = True,
) -> GovernanceGateReport:
    changes = _change_set(root, path)
    return build_governance_gate_report(
        repository_root=root,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(root)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(constitution_pass),
        deterministic_quality_gate=_quality_report(
            root, change_set=changes, passed=quality_pass
        ),
        change_set=changes,
        approval_records=records,
        require_change_set=True,
        enforce_approval=True,
    )


def _record(root: Path, policy: SoleOwnerPolicy, *, path: str = PATH) -> ApprovalRecord:
    source = _report(root, path=path)
    assert source.subject_digest is not None
    assert source.deterministic_quality_gate is not None
    now = datetime.now(UTC)
    return ApprovalRecord(
        WorkflowIdentity("TEST_ONLY_WORK", "TEST_ONLY_RUN", "TEST_ONLY_TRACE", now),
        "TEST_ONLY_APPROVAL",
        policy.owner_principal_id,
        "TEST_ONLY_SUBJECT",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("TEST_ONLY_EVIDENCE",),
        approver_role=(
            "ConstitutionOwner"
            if path.startswith("docs/governance/")
            else "GovernanceOwner"
        ),
        principal_id=policy.owner_principal_id,
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256=source.subject_digest.subject_id,
        scope_hash=_change_set(root, path).change_set_sha256,
        quality_gate_evidence_sha256=(
            source.deterministic_quality_gate.gate_evidence_sha256
        ),
        governance_gate_evidence_sha256=source.gate_evidence_sha256,
        evidence_hash=_approval_evidence_hash(
            source.deterministic_quality_gate, source
        ),
        authority_family_sha256=source.subject_digest.authority_family_sha256,
        lifecycle_definition_sha256=_lifecycle_definition_sha256(),
        approved_at=now,
        expires_at=now + timedelta(minutes=10),
        sole_owner_confirmation=SoleOwnerConfirmation(
            policy.owner_person_id,
            policy.owner_principal_id,
            policy.policy_sha256,
            policy.activation_sha256,
        ),
    )


def test_inactive_model_preserves_current_two_person_c3_rule(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert load_sole_owner_policy(root) is None
    monkeypatch.setattr(
        "ai4binance.governance.gate.load_sole_owner_policy",
        lambda _root, policy_commit=None: None,
    )
    report = _report(root)
    assert report.approval_verification is not None
    assert report.approval_verification.required_approval_count == 2
    assert report.approval_verification.approval_profile == "LEGACY_C3"


def test_c4_high_assurance_requirement_is_unchanged() -> None:
    assert _approval_requirements(ChangeApprovalClass.C4_CONSEQUENTIAL) == (
        1,
        True,
        True,
    )


def test_framework_restricts_accepted_owner_model_to_c3() -> None:
    from ai4binance.governance.framework import ConstitutionalChangeControl

    control = ConstitutionalChangeControl()
    assert control.sole_owner_approval_change_classes == (
        ChangeApprovalClass.C3_GOVERNED,
    )
    with pytest.raises(ValueError, match="restricted to C3"):
        replace(
            control,
            sole_owner_approval_change_classes=(ChangeApprovalClass.C4_CONSEQUENTIAL,),
        )


def test_one_registered_principal_can_approve_later_c3_only(
    root: Path, policy: SoleOwnerPolicy
) -> None:
    report = _report(root, (_record(root, policy),))
    approval = report.approval_verification
    assert approval is not None
    assert approval.status is ApprovalVerificationStatus.PASS
    assert approval.required_approval_count == approval.observed_approval_count == 1
    assert approval.approval_profile == "SOLE_HUMAN_OWNER"
    assert approval.independent_human_review is False
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: replace(record, approver_role="ConstitutionOwner"),
        lambda record: replace(record, principal_id="TEST_ONLY_OTHER"),
        lambda record: replace(record, sole_owner_confirmation=None),
        lambda record: replace(record, scope_hash="0" * 64),
        lambda record: replace(record, subject_sha256="0" * 64),
        lambda record: replace(record, evidence_hash="0" * 64),
        lambda record: replace(record, authority_family_sha256="0" * 64),
        lambda record: replace(
            record,
            approved_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        ),
        lambda record: replace(record, status=ApprovalStatus.APPROVED_FOR_RESEARCH),
    ],
)
def test_wrong_role_identity_or_exact_binding_fails_closed(
    root: Path,
    policy: SoleOwnerPolicy,
    mutate: Callable[[ApprovalRecord], ApprovalRecord],
) -> None:
    changed = mutate(_record(root, policy))
    report = _report(root, (changed,))
    assert report.approval_verification is not None
    assert (
        report.approval_verification.status
        is ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    )


@pytest.mark.parametrize(
    "path", [POLICY_PATH, "docs/governance/framework_core_vnext_governance.md"]
)
def test_accepted_policy_allows_later_model_maintenance(
    root: Path, policy: SoleOwnerPolicy, path: str
) -> None:
    record = _record(root, policy, path=path)
    report = _report(root, (record,), path=path)
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert report.approval_verification.required_approval_count == 1
    assert report.approval_verification.approval_profile == "SOLE_HUMAN_OWNER"


def test_unaccepted_successor_cannot_change_approval_count(
    root: Path, policy: SoleOwnerPolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[str | None] = []

    def accepted_only(
        _root: Path, *, policy_commit: str | None = None
    ) -> SoleOwnerPolicy:
        observed.append(policy_commit)
        return policy

    monkeypatch.setattr(
        "ai4binance.governance.gate.load_sole_owner_policy", accepted_only
    )
    candidate = root / POLICY_PATH
    candidate.write_text("activation_status: INACTIVE\n", encoding="utf-8")
    record = _record(root, policy, path=POLICY_PATH)
    report = _report(root, (record,), path=POLICY_PATH)
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert observed
    assert all(commit is not None for commit in observed)


def test_failed_mandatory_checks_still_veto(
    root: Path, policy: SoleOwnerPolicy
) -> None:
    record = _record(root, policy)
    quality = _report(root, (record,), quality_pass=False)
    assert "DETERMINISTIC_QUALITY_GATE_NOT_PASSING" in quality.blockers
    constitution = _report(root, (record,), constitution_pass=False)
    assert constitution.constitution_sync.status == "RUNNING_WITH_BLOCKERS"


def test_later_candidate_byte_change_invalidates_approval(
    root: Path, policy: SoleOwnerPolicy
) -> None:
    record = _record(root, policy)
    (root / PATH).write_text("Test-only changed governed bytes.\n", encoding="utf-8")
    report = _report(root, (record,))
    assert "APPROVAL_SUBJECT_MISMATCH:TEST_ONLY_APPROVAL" in report.blockers


def test_missing_owner_decision_is_not_supplied_by_automated_evidence(
    root: Path, policy: SoleOwnerPolicy
) -> None:
    report = _report(root)
    assert "APPROVAL_REQUIRED" in report.blockers
    assert report.execution_allowed is False


@pytest.mark.parametrize("principal", ["TEST_ONLY_MODEL", "TEST_ONLY_AUDIT_BOT"])
def test_automated_reviewer_is_not_the_registered_human(
    root: Path, policy: SoleOwnerPolicy, principal: str
) -> None:
    record = replace(
        _record(root, policy), approver_id=principal, principal_id=principal
    )
    assert "SOLE_OWNER_PRINCIPAL_OR_ROLE_MISMATCH" in _report(root, (record,)).blockers


def test_individual_owner_approval_remains_revocable(
    root: Path, policy: SoleOwnerPolicy
) -> None:
    record = replace(_record(root, policy), revoked_at=datetime.now(UTC))
    assert "APPROVAL_REVOKED:TEST_ONLY_APPROVAL" in _report(root, (record,)).blockers


def test_same_allowed_repair_paths_with_different_bytes_are_rejected() -> None:
    from ai4binance.governance.personal_research import (
        FROZEN_REPAIR_BASELINE,
        FROZEN_REPAIR_OUTPUTS,
        FROZEN_REPAIR_TREE,
        verify_frozen_initial_repair,
    )
    from tests.test_personal_research_governance import ROOT

    inventory = json.loads(
        (
            ROOT
            / "runtime/artifacts/quality/minimal-two-fix-successor-20261002"
            / "inventory.json"
        ).read_bytes()
    )
    patch = (ROOT / inventory["patch_path"]).read_bytes()
    # Establish the accepted content boundary before changing only an output hash.
    verify_frozen_initial_repair(
        ROOT,
        patch,
        expected_root=ROOT.resolve().as_posix(),
        baseline_commit=FROZEN_REPAIR_BASELINE,
        expected_tree=FROZEN_REPAIR_TREE,
        outputs=FROZEN_REPAIR_OUTPUTS,
        change_class="C3_GOVERNED",
    )
    changed = dict(FROZEN_REPAIR_OUTPUTS)
    first = next(iter(changed))
    changed[first] = "0" * 64
    with pytest.raises(ValueError, match="INITIAL_REPAIR_NOT_EXACT_SUBJECT"):
        verify_frozen_initial_repair(
            ROOT,
            patch,
            expected_root=ROOT.resolve().as_posix(),
            baseline_commit=FROZEN_REPAIR_BASELINE,
            expected_tree=FROZEN_REPAIR_TREE,
            outputs=changed,
            change_class="C3_GOVERNED",
        )


def test_activation_cannot_be_enabled_without_registered_principal(
    root: Path,
) -> None:
    policy_path = root / POLICY_PATH
    text = policy_path.read_text(encoding="utf-8")
    policy_path.write_text(text.replace("INACTIVE", "ACTIVE"), encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        load_sole_owner_policy(root)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_v5_rejects_substituted_adoption_commit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.governance import sole_owner

    activation, contents = _synthetic_activation(root, monkeypatch)
    adopted = str(activation["adoption_commit"])
    replacement = "d" * 40
    original_git = sole_owner._git
    path = "src/ai4binance/governance/sole_owner.py"
    substituted = contents[path] + b"\nTEST_ONLY_UNREVIEWED_CHANGE"

    def git_fact(repository: Path, *args: str) -> bytes:
        if args == ("show", replacement + ":" + path):
            return substituted
        mapped = tuple(arg.replace(replacement, adopted) for arg in args)
        return original_git(repository, *mapped)

    monkeypatch.setattr(sole_owner, "_git", git_fact)
    activation["adoption_commit"] = replacement
    cast("dict[str, str]", activation["candidate_files"])[path] = _hash(substituted)
    with pytest.raises(ValueError, match=r"COMMITTED_REVIEW_|TEST_ONLY_CANONICAL_"):
        sole_owner._verify_adoption(root, activation, datetime.now(UTC))


def test_v5_rejects_direct_active_adoption_without_activation_receipt(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.governance import sole_owner

    activation, _ = _synthetic_activation(root, monkeypatch)
    active = (root / POLICY_PATH).read_bytes()
    cast("dict[str, str]", activation["candidate_files"])[POLICY_PATH] = _hash(active)
    activation.pop("activation_acceptance", None)
    with pytest.raises(
        ValueError, match="SOLE_OWNER_INITIAL_ACTIVATION_ACCEPTANCE_REQUIRED"
    ):
        sole_owner._verify_successor(root, activation, active, None, datetime.now(UTC))


def _test_only_preceding_founding_rule(root: Path, *, operative: bool = True) -> None:
    """Simulate an already operative founding amendment, never current authority."""
    from ai4binance.governance import sole_owner

    paths = sole_owner.RECONCILIATION_PATHS | {
        sole_owner.CORE_PATH,
        "docs/compliance/registry_compliance_matrix.md",
    }
    entries = []
    for index, path in enumerate(sorted(paths)):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (
            (_candidate_path(path)).read_bytes()
            if path == sole_owner.CORE_PATH
            else (
                f"---\ndocument_id: TEST_ONLY_{index}\nversion: 0.0.0\n"
                "---\nTEST_ONLY predecessor\n"
            ).encode()
        )
        if path == sole_owner.CORE_PATH:
            data = re.sub(
                rb"^version: .+$", b"version: 3.0.0", data, count=1, flags=re.M
            )
        if path == sole_owner.CORE_PATH and not operative:
            data = data.replace(
                sole_owner.INITIAL_AMENDMENT_CLAUSE.encode(),
                b"TEST_ONLY_UNRECOGNIZED_CONTRACT",
            )
        target.write_bytes(data)
        entries.append(
            {
                "path": path,
                "version": "0.0.0",
                "sha256": _hash(data),
                "expected_hash": _hash(data),
            }
        )
    target = root / "config/governance/governed_document_lock_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"locked_documents": entries, "approval_records": []}) + "\n"
    )


def _test_only_registration_outputs(root: Path, contents: dict[str, str]) -> None:
    from ai4binance.governance import sole_owner
    from ai4binance.governance.repository_validator import _frontmatter

    paths = sole_owner.RECONCILIATION_PATHS | {
        sole_owner.CORE_PATH,
        "docs/compliance/registry_compliance_matrix.md",
    }
    entries = []
    for path in sorted(paths):
        target = root / path
        target.write_bytes((_candidate_path(path)).read_bytes())
        contents[path] = _hash(target.read_bytes())
        metadata = _frontmatter(target)
        assert metadata is not None
        entries.append(
            {
                "path": path,
                "version": metadata["version"],
                "sha256": contents[path],
                "expected_hash": contents[path],
            }
        )
    path = "config/governance/governed_document_lock_manifest.json"
    contents[path] = _write_json(
        root, path, {"locked_documents": entries, "approval_records": []}
    )


def _test_only_initial_amendment(
    root: Path,
    activation: dict[str, object],
    *,
    receipt: dict[str, object] | None = None,
) -> dict[str, str]:
    """All human sources, reviews and completion below are TEST_ONLY simulations."""
    from ai4binance.governance import sole_owner
    from ai4binance.governance.repository_validator import _frontmatter

    phase = "ADOPTION" if receipt is None else "ACTIVATION"
    current = activation if receipt is None else receipt
    base = str(current["adoption_base_commit" if receipt is None else "base_commit"])
    subject = str(current["adoption_subject_id" if receipt is None else "subject_id"])
    governing = sole_owner._git(root, "show", f"{base}:{sole_owner.CORE_PATH}")
    if receipt is None:
        patch_sha = str(activation["adoption_patch_sha256"])
    else:
        frozen = json.loads((root / str(receipt["frozen_gate_ref"])).read_text())
        patch_sha = frozen["change_set"]["review_patch_sha256"]
    prefix = f"runtime/artifacts/governance/TEST_ONLY_{phase}_"

    def reference(path: str) -> dict[str, str]:
        return {"path": path, "sha256": _hash((root / path).read_bytes())}

    primary = prefix + "primary.txt"
    (root / primary).write_text(
        "TEST_ONLY simulated owner source; no real human decision.\n"
    )
    decision = {
        "contract_version": "InitialOwnerDecision/v1",
        "record_origin": "OWNER_ISSUED",
        "decision": "ADOPT_EXACT_INITIAL_OWNER_AMENDMENT",
        "decision_id": f"TEST_ONLY_{phase}",
        "owner_person_id": "Huseyin Cicek",
        "owner_principal_id": "TEST_ONLY_0",
        "subject_sha256": subject,
        "phase": phase,
        "baseline_commit": base,
        "patch_sha256": patch_sha,
        "primary_owner_source": reference(primary),
        "independent_human_review": False,
        "execution_allowed": False,
    }
    _write_json(root, prefix + "decision.json", decision)
    now = datetime.now(UTC)
    if receipt is None:
        superior = prefix + "superior.md"
        (root / superior).write_bytes(governing)
        report = prefix + "content-review.md"
        (root / report).write_text(
            "TEST_ONLY complete-content fixture review; no real approval.\n"
        )
        rows, payloads = [], []
        documents = sole_owner.RECONCILIATION_PATHS | {
            sole_owner.CORE_PATH,
            "docs/compliance/registry_compliance_matrix.md",
        }
        for index, path in enumerate(sorted(documents)):
            data = (root / path).read_bytes()
            source = prefix + f"document-{index}.md"
            (root / source).write_bytes(data)
            metadata = _frontmatter(root / path)
            assert metadata is not None
            rows.append(
                {
                    "path": path,
                    "document_id": metadata["document_id"],
                    "version": metadata["version"],
                    "sha256": _hash(data),
                    "reviewed_current_content": True,
                    "historical_integrity_proved": False,
                    "content_review": reference(report),
                    "provenance_status": "GOVERNING_AMENDMENT",
                }
            )
            payloads.append({"path": path, "source": reference(source)})
        registration = prefix + "registration.json"
        (root / registration).write_bytes(
            (
                root / "config/governance/governed_document_lock_manifest.json"
            ).read_bytes()
        )
        protected = prefix + "protected-review.json"
        _write_json(
            root,
            protected,
            {
                "contract_version": "InitialProtectedReview/v1",
                "baseline_commit": base,
                "superior_authority": reference(superior),
                "registration_manifest": reference(registration),
                "documents": rows,
                "candidate_payloads": payloads,
            },
        )
    else:
        adoption = json.loads(
            (
                root
                / str(cast("dict[str,str]", activation["initial_amendment"])["path"])
            ).read_text()
        )
        protected = adoption["protected_review"]["path"]
    _write_json(
        root,
        prefix + "revocations.json",
        {
            "contract_version": "DocumentLockReviewRevocations/v1",
            "repository_root": root.resolve().as_posix(),
            "epoch_id": "TEST_ONLY",
            "issued_at_utc": now.isoformat(),
            "not_before_utc": now.isoformat(),
            "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
            "revoked_decision_ids": [],
            "revoked_owner_ids": [],
            "revoked_subjects": [],
        },
    )
    value = {
        "contract_version": "InitialOwnerAmendment/v1",
        "record_origin": "OWNER_ISSUED",
        "status": "ISSUED",
        "decision_id": decision["decision_id"],
        "repository_root": root.resolve().as_posix(),
        "owner_person_id": decision["owner_person_id"],
        "owner_principal_id": "TEST_ONLY_0",
        "subject_sha256": subject,
        "phase": phase,
        "baseline_commit": base,
        "governing_core_version": (
            _required_core_version(root / sole_owner.CORE_PATH) if receipt else "3.0.0"
        ),
        "governing_core_sha256": _hash(governing),
        "patch_sha256": patch_sha,
        "candidate_files": current["candidate_files"],
        "decision_source": reference(prefix + "decision.json"),
        "protected_review": reference(protected),
        "revocations": reference(prefix + "revocations.json"),
        "custody": {
            "custodian_person_id": "Huseyin Cicek",
            "checked_at_utc": now.isoformat(),
            "decision_channel": "TEST_ONLY fixture, not an authenticated channel",
            "primary_owner_source": reference(primary),
        },
        "issued_at_utc": (now - timedelta(minutes=10)).isoformat(),
        "not_before_utc": (now - timedelta(minutes=10)).isoformat(),
        "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
        "revoked_at_utc": None,
        "scope": "LOCAL_RESEARCH_PAPER_INITIAL_TRANSITION",
        "excluded_effects": [
            "LIVE_EXECUTION",
            "DEPLOYMENT",
            "CREDENTIALS",
            "INFRASTRUCTURE",
            "RISK_OVERRIDE",
            "PROMOTION",
            "C4_CONSEQUENTIAL",
        ],
        "independent_human_review": False,
        "execution_allowed": False,
    }
    for name, adoption_key, activation_key in (
        ("quality_gate_evidence_sha256", "adoption_quality_sha256", "quality_sha256"),
        (
            "governance_gate_evidence_sha256",
            "adoption_governance_sha256",
            "governance_sha256",
        ),
        ("evidence_hash", "adoption_evidence_hash", "evidence_hash"),
        (
            "authority_family_sha256",
            "adoption_authority_family_sha256",
            "authority_family_sha256",
        ),
        (
            "lifecycle_definition_sha256",
            "adoption_lifecycle_sha256",
            "lifecycle_definition_sha256",
        ),
    ):
        value[name] = current[adoption_key if receipt is None else activation_key]
    if receipt is not None:
        completion = prefix + "adoption-completion.json"
        _write_json(
            root,
            completion,
            {
                "contract_version": "InitialOwnerCompletion/v1",
                "status": "COMPLETED",
                "phase": "ADOPTION",
                "owner_principal_id": "TEST_ONLY_0",
                "baseline_commit": activation["adoption_base_commit"],
                "accepted_commit": base,
                "subject_sha256": activation["adoption_subject_id"],
                "patch_sha256": activation["adoption_patch_sha256"],
                "candidate_files": activation["candidate_files"],
                "amendment": activation["initial_amendment"],
                "protected_review": reference(protected),
                "completed_at_utc": activation["adoption_accepted_at_utc"],
                "execution_allowed": False,
            },
        )
        value["adoption_completion"] = reference(completion)
    path = prefix + "amendment.json"
    binding = sole_owner.initial_decision_binding(value)
    (root / primary).write_text(
        "TEST_ONLY simulated owner decision; never actual approval.\n"
        f"INITIAL_OWNER_DECISION {binding}\n"
    )
    decision["decision_binding_sha256"] = binding
    decision["primary_owner_source"] = reference(primary)
    _write_json(root, prefix + "decision.json", decision)
    custody = cast("dict[str, object]", value["custody"])
    custody["primary_owner_source"] = reference(primary)
    value["decision_source"] = reference(prefix + "decision.json")
    _write_json(root, path, value)
    return reference(path)


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "missing",
        "wrong_principal",
        "expired",
        "revoked",
        "revoked_owner",
        "revoked_subject",
        "patch",
        "unreviewed",
        "hash_only",
        "review_drift",
        "source_drift",
        "output_drift",
        "extra_scope",
        "quality_veto",
        "validation_veto",
        "wrong_approval_principal",
        "expired_approval",
        "revoked_approval",
    ],
)
def test_initial_owner_adoption_with_real_git(tmp_path: Path, mutation: str) -> None:
    """Conditional proposal proof: a TEST_ONLY predecessor already recognizes it."""
    from ai4binance.governance import sole_owner

    activation = _real_git_adoption(tmp_path, founding=True)
    reference = cast("dict[str,str]", activation["initial_amendment"])
    path = tmp_path / reference["path"]
    value = json.loads(path.read_text())
    if mutation == "missing":
        activation.pop("initial_amendment")
    elif mutation in ("wrong_principal", "expired", "revoked", "patch", "extra_scope"):
        key, new = {
            "wrong_principal": ("owner_principal_id", "TEST_ONLY_WRONG_PERSON"),
            "expired": (
                "expires_at_utc",
                (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            ),
            "revoked": ("revoked_at_utc", datetime.now(UTC).isoformat()),
            "patch": ("patch_sha256", "0" * 64),
            "extra_scope": ("scope", "LIVE_EXECUTION"),
        }[mutation]
        value[key] = new
    elif mutation.startswith("revoked_"):
        r = value["revocations"]
        snapshot = json.loads((tmp_path / r["path"]).read_text())
        field = (
            "revoked_owner_ids" if mutation == "revoked_owner" else "revoked_subjects"
        )
        snapshot[field] = [
            value["owner_person_id"]
            if mutation == "revoked_owner"
            else value["subject_sha256"]
        ]
        r["sha256"] = _write_json(tmp_path, r["path"], snapshot)
    elif mutation in ("unreviewed", "hash_only", "review_drift"):
        r = value["protected_review"]
        review = json.loads((tmp_path / r["path"]).read_text())
        if mutation == "unreviewed":
            review["documents"][0]["reviewed_current_content"] = False
        elif mutation == "hash_only":
            review["documents"][0].pop("content_review")
        else:
            evidence = tmp_path / review["documents"][0]["content_review"]["path"]
            evidence.write_text("TEST_ONLY unauthorized changed review\n")
        r["sha256"] = _write_json(tmp_path, r["path"], review)
    elif mutation == "source_drift":
        source = (
            tmp_path / "runtime/artifacts/governance/TEST_ONLY_ADOPTION_primary.txt"
        )
        source.write_text("TEST_ONLY no bound owner decision\n")
    elif mutation == "output_drift":
        cast("dict[str,str]", activation["candidate_files"])[POLICY_PATH] = "0" * 64
    elif mutation in ("quality_veto", "validation_veto"):
        r = str(activation["frozen_gate_ref"])
        frozen = json.loads((tmp_path / r).read_text())
        frozen[
            "deterministic_quality_gate"
            if mutation == "quality_veto"
            else "repository_validator_gate"
        ]["status"] = "FAIL"
        activation["frozen_gate_sha256"] = _write_json(tmp_path, r, frozen)
    elif mutation in (
        "wrong_approval_principal",
        "expired_approval",
        "revoked_approval",
    ):
        r = str(activation["approval_records_ref"])
        records = json.loads((tmp_path / r).read_text())
        first = records["approval_records"][0]
        if mutation == "wrong_approval_principal":
            first["principal_id"] = "TEST_ONLY_WRONG_PERSON"
            first["approver_id"] = "TEST_ONLY_WRONG_PERSON"
        elif mutation == "expired_approval":
            first["expires_at_utc"] = (
                datetime.now(UTC) - timedelta(minutes=1)
            ).isoformat()
        else:
            first["revoked_at_utc"] = datetime.now(UTC).isoformat()
        activation["approval_records_sha256"] = _write_json(tmp_path, r, records)
    if mutation in ("unreviewed", "hash_only"):
        # Rebind the simulated owner source so the content-review contract,
        # rather than a stale source hash, must reject the unsafe proposal.
        source_path = str(value["decision_source"]["path"])
        source = json.loads((tmp_path / source_path).read_text())
        primary = str(source["primary_owner_source"]["path"])
        binding = sole_owner.initial_decision_binding(value)
        (tmp_path / primary).write_text(
            f"TEST_ONLY simulated owner decision\nINITIAL_OWNER_DECISION {binding}\n"
        )
        source["decision_binding_sha256"] = binding
        source["primary_owner_source"]["sha256"] = _hash(
            (tmp_path / primary).read_bytes()
        )
        value["custody"]["primary_owner_source"] = source["primary_owner_source"]
        value["decision_source"]["sha256"] = _write_json(tmp_path, source_path, source)
    if "initial_amendment" in activation:
        reference["sha256"] = _write_json(tmp_path, reference["path"], value)
    if mutation == "none":
        sole_owner._verify_adoption(tmp_path, activation, datetime.now(UTC))
        records = json.loads(
            (tmp_path / str(activation["approval_records_ref"])).read_text()
        )
        assert len(records["approval_records"]) == 1
        assert not (tmp_path / sole_owner.INITIAL_AMENDMENT_PATH).exists()
    else:
        with pytest.raises(
            ValueError, match=r"SOLE_OWNER_|DOCUMENT_REVIEW_|instance validation failed"
        ):
            sole_owner._verify_adoption(tmp_path, activation, datetime.now(UTC))


def test_initial_candidate_cannot_create_preceding_authority(tmp_path: Path) -> None:
    """Current Core 2.0.6 has no founding route even with a complete candidate."""
    from ai4binance.governance import sole_owner

    activation = _real_git_adoption(tmp_path, founding=True, operative=False)
    current_core = sole_owner._git(
        tmp_path,
        "show",
        f"{activation['adoption_base_commit']}:{sole_owner.CORE_PATH}",
    )
    assert sole_owner.INITIAL_AMENDMENT_CLAUSE.encode() not in current_core.splitlines()
    ref = cast("dict[str,str]", activation["initial_amendment"])
    with pytest.raises(ValueError, match="SOLE_OWNER_FOUNDING_AUTHORITY_NOT_OPERATIVE"):
        sole_owner.verify_initial_owner_amendment(
            tmp_path,
            ref,
            base=str(activation["adoption_base_commit"]),
            subject_id=str(activation["adoption_subject_id"]),
            patch_sha256=str(activation["adoption_patch_sha256"]),
            candidate_files=cast("dict[str,str]", activation["candidate_files"]),
            phase="ADOPTION",
            now=datetime.now(UTC),
            accepted=str(activation["adoption_commit"]),
        )


def test_initial_owner_decision_cannot_be_reused_for_a_new_baseline(
    tmp_path: Path,
) -> None:
    from ai4binance.governance import sole_owner

    activation = _real_git_adoption(tmp_path, founding=True)
    ref = cast("dict[str,str]", activation["initial_amendment"])
    target = tmp_path / sole_owner.INITIAL_AMENDMENT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((tmp_path / ref["path"]).read_bytes())
    with pytest.raises(ValueError, match="SOLE_OWNER_INITIAL_AMENDMENT_SUBJECT_DRIFT"):
        sole_owner.load_initial_owner_amendment(
            tmp_path,
            base=str(activation["adoption_commit"]),
            subject_id=str(activation["adoption_subject_id"]),
            patch_sha256=str(activation["adoption_patch_sha256"]),
            candidate_files=cast("dict[str,str]", activation["candidate_files"]),
            now=datetime.now(UTC),
        )


@pytest.mark.parametrize(
    "mutation", ["none", "missing", "incomplete", "replay", "wrong_principal"]
)
def test_initial_owner_activation_with_real_git(tmp_path: Path, mutation: str) -> None:
    activation, activation_ref = _real_git_transition(
        tmp_path, "initial", founding=True
    )
    receipt = cast("dict[str,object]", activation["activation_acceptance"])
    ref = cast("dict[str,str]", receipt["initial_amendment"])
    value = json.loads((tmp_path / ref["path"]).read_text())
    if mutation == "missing":
        receipt.pop("initial_amendment")
    elif mutation == "incomplete":
        value.pop("adoption_completion")
    elif mutation == "replay":
        receipt["initial_amendment"] = activation["initial_amendment"]
    elif mutation == "wrong_principal":
        value["owner_principal_id"] = "TEST_ONLY_WRONG_PERSON"
    if mutation in ("incomplete", "wrong_principal"):
        ref["sha256"] = _write_json(tmp_path, ref["path"], value)
    _write_json(tmp_path, activation_ref, activation)
    if mutation == "none":
        selected = load_sole_owner_policy(tmp_path)
        assert selected is not None
        assert selected.owner_principal_id == "TEST_ONLY_0"
        policy = yaml.safe_load((tmp_path / POLICY_PATH).read_text())
        assert policy["execution_allowed"] is False
        assert policy["promotion_status"] == "RESEARCH_ONLY"
        assert policy["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    else:
        with pytest.raises(
            ValueError, match=r"SOLE_OWNER_|DOCUMENT_REVIEW_|JSON_SCHEMA_"
        ):
            load_sole_owner_policy(tmp_path)


@pytest.mark.parametrize("quality_pass", [True, False])
def test_initial_owner_canonical_approval_consumer(
    tmp_path: Path, quality_pass: bool
) -> None:
    """Actual gate wiring with real Git, schema and TEST_ONLY human evidence."""
    from ai4binance.governance import gate as gate_module
    from ai4binance.governance import sole_owner

    activation = _real_git_adoption(tmp_path, founding=True)
    write_quality_evidence(tmp_path)
    changes = gate_module.resolve_committed_governance_change_set(
        tmp_path,
        str(activation["adoption_base_commit"]),
        str(activation["adoption_commit"]),
    )

    def report(records: tuple[ApprovalRecord, ...] = ()) -> GovernanceGateReport:
        return build_governance_gate_report(
            repository_root=tmp_path,
            repository_validator=load_repository_validator_evidence(
                _write_validator_report(tmp_path)
            ),
            docs_hygiene=_docs_hygiene(True),
            artifact_hygiene=_artifact_hygiene(True),
            constitution_sync_tests=_constitution_sync_tests(True),
            deterministic_quality_gate=_quality_report(
                tmp_path, change_set=changes, passed=quality_pass
            ),
            change_set=changes,
            approval_records=records,
            require_change_set=True,
            enforce_approval=True,
        )

    context_path = tmp_path / sole_owner.INITIAL_AMENDMENT_PATH
    context_path.parent.mkdir(parents=True, exist_ok=True)
    ref = cast("dict[str,str]", activation["initial_amendment"])
    context_path.write_bytes((tmp_path / ref["path"]).read_bytes())
    source = report()
    assert source.subject_digest is not None
    assert source.deterministic_quality_gate is not None
    activation.update(
        adoption_subject_id=source.subject_digest.subject_id,
        adoption_quality_sha256=source.deterministic_quality_gate.gate_evidence_sha256,
        adoption_governance_sha256=source.gate_evidence_sha256,
        adoption_evidence_hash=_approval_evidence_hash(
            source.deterministic_quality_gate, source
        ),
        adoption_authority_family_sha256=source.subject_digest.authority_family_sha256,
        adoption_lifecycle_sha256=_lifecycle_definition_sha256(),
    )
    ref = _test_only_initial_amendment(tmp_path, activation)
    context_path.write_bytes((tmp_path / ref["path"]).read_bytes())
    payload = json.loads(
        (tmp_path / str(activation["approval_records_ref"])).read_text()
    )
    record = payload["approval_records"][0]
    for field, key in (
        ("subject_sha256", "adoption_subject_id"),
        ("quality_gate_evidence_sha256", "adoption_quality_sha256"),
        ("governance_gate_evidence_sha256", "adoption_governance_sha256"),
        ("evidence_hash", "adoption_evidence_hash"),
        ("authority_family_sha256", "adoption_authority_family_sha256"),
        ("lifecycle_definition_sha256", "adoption_lifecycle_sha256"),
    ):
        record[field] = activation[key]
    _write_json(tmp_path, str(activation["approval_records_ref"]), payload)
    observed = report(
        gate_module.load_approval_records(
            tmp_path / str(activation["approval_records_ref"])
        )
    )
    assert observed.approval_verification is not None
    assert observed.approval_verification.required_approval_count == 1
    assert observed.approval_verification.approval_profile == "INITIAL_OWNER_AMENDMENT"
    assert observed.approval_verification.status is ApprovalVerificationStatus.PASS
    assert observed.approval_verification.independent_human_review is False
    if not quality_pass:
        assert observed.deterministic_gate_resolver.decision.value == "BLOCKED"
        assert observed.execution_allowed is False
    assert observed.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _real_git_adoption(
    root: Path, *, founding: bool = False, operative: bool = True
) -> dict[str, object]:
    """Real isolated Git facts, but TEST_ONLY approvals and technical evidence."""
    from ai4binance.governance import gate as gate_module
    from ai4binance.governance import sole_owner
    from tests.test_governance_gate import _git_for_committed_review as git

    git(root, "init")
    git(root, "config", "user.name", "TEST_ONLY")
    git(root, "config", "user.email", "test-only@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / ".gitignore").write_text("runtime/\n", encoding="utf-8")
    if founding:
        _test_only_preceding_founding_rule(root, operative=operative)
    git(root, "add", ".")
    git(root, "commit", "-m", "TEST_ONLY predecessor")
    base = git(root, "rev-parse", "HEAD")
    contents = {}
    for relative in sorted(MODEL_CONTROL_PATHS):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (
            (_candidate_path(relative)).read_bytes()
            if relative in (POLICY_PATH, SCHEMA_PATH) or founding
            else b"TEST_ONLY proposed content\n"
        )
        target.write_bytes(data)
        contents[relative] = _hash(data)
    if founding:
        _test_only_registration_outputs(root, contents)
    git(root, "add", ".")
    git(root, "commit", "-m", "TEST_ONLY inactive adoption")
    accepted = git(root, "rev-parse", "HEAD")
    change = gate_module.resolve_committed_governance_change_set(root, base, accepted)
    subject = gate_module._build_governance_subject_digest(root, change).to_payload()
    patch = sole_owner._git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--no-textconv",
        "--find-renames=50%",
        "--abbrev=8",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--diff-algorithm=default",
        base,
        accepted,
    )
    assert _hash(patch) == change.review_patch_sha256
    patch_ref = "runtime/artifacts/governance/TEST_ONLY_commit.patch"
    (root / patch_ref).parent.mkdir(parents=True)
    (root / patch_ref).write_bytes(patch)
    gate_ref = (
        "runtime/artifacts/quality/gate/runs/TEST_ONLY_REAL_GIT/"
        "governance-gate-approval-required.json"
    )
    frozen = {
        "status": "RUNNING_WITH_BLOCKERS",
        "blockers": ["APPROVAL_REQUIRED"],
        "change_set": change.to_payload(),
        "subject_digest": subject,
        "gate_evidence_sha256": "4" * 64,
        "approval_verification": {
            "required_approval_count": 2,
            "approval_profile": "LEGACY_C3",
        },
        "deterministic_quality_gate": {
            "status": "PASS",
            "gate_evidence_sha256": "3" * 64,
        },
        **{
            key: {"status": "PASS"}
            for key in (
                "repository_hygiene",
                "constitution_sync",
                "repository_conformance",
                "repository_validator_gate",
            )
        },
    }
    records = []
    for number, role in enumerate(["GovernanceOwner", "ConstitutionOwner"]):
        records.append(
            {
                "approval_id": f"TEST_ONLY_{number}",
                "approver_id": f"TEST_ONLY_{number}",
                "principal_id": f"TEST_ONLY_{number}",
                "approver_role": role,
                "subject_ref": gate_ref,
                "status": "APPROVED_FOR_IMPLEMENTATION",
                "evidence_refs": ["TEST_ONLY_EVIDENCE"],
                "change_class": "C3_GOVERNED",
                "subject_sha256": subject["subject_id"],
                "scope_hash": change.change_set_sha256,
                "quality_gate_evidence_sha256": "3" * 64,
                "governance_gate_evidence_sha256": "4" * 64,
                "evidence_hash": "5" * 64,
                "authority_family_sha256": subject["authority_family_sha256"],
                "lifecycle_definition_sha256": "7" * 64,
                "approved_at_utc": (
                    datetime.now(UTC) - timedelta(minutes=5)
                ).isoformat(),
                "expires_at_utc": (
                    datetime.now(UTC) + timedelta(minutes=30)
                ).isoformat(),
            }
        )
    approval_ref = "runtime/artifacts/governance/TEST_ONLY_records.json"
    activation = {
        "adoption_base_commit": base,
        "adoption_commit": accepted,
        "candidate_files": contents,
        "adoption_patch_ref": patch_ref,
        "adoption_patch_sha256": _hash(patch),
        "frozen_gate_ref": gate_ref,
        "frozen_gate_sha256": _write_json(root, gate_ref, frozen),
        "approval_records_ref": approval_ref,
        "approval_records_sha256": _write_json(
            root, approval_ref, {"approval_records": records}
        ),
        "adoption_subject_id": subject["subject_id"],
        "adoption_scope_hash": change.change_set_sha256,
        "adoption_quality_sha256": "3" * 64,
        "adoption_governance_sha256": "4" * 64,
        "adoption_evidence_hash": "5" * 64,
        "adoption_authority_family_sha256": subject["authority_family_sha256"],
        "adoption_lifecycle_sha256": "7" * 64,
    }
    if founding:
        activation["initial_amendment"] = _test_only_initial_amendment(root, activation)
        frozen["approval_verification"] = {
            "required_approval_count": 1,
            "approval_profile": "INITIAL_OWNER_AMENDMENT",
        }
        records = [records[0]]
        records[0]["approver_role"] = "ConstitutionOwner"
        records[0]["evidence_refs"] = [
            "runtime/artifacts/governance/TEST_ONLY_ADOPTION_decision.json"
        ]
        activation["frozen_gate_sha256"] = _write_json(root, gate_ref, frozen)
        activation["approval_records_sha256"] = _write_json(
            root, approval_ref, {"approval_records": records}
        )
    return activation


@pytest.mark.parametrize(
    "mutation",
    ["none", "commit", "patch", "subject", "review_head", "active", "content"],
)
def test_real_git_adoption_exact_binding(tmp_path: Path, mutation: str) -> None:
    """No Git or canonical consumer mocks; no real human authority asserted."""
    from ai4binance.governance import sole_owner
    from tests.test_governance_gate import _git_for_committed_review as git

    activation = _real_git_adoption(tmp_path)
    adopted = str(activation["adoption_commit"])
    path = (
        POLICY_PATH
        if mutation == "active"
        else "src/ai4binance/governance/sole_owner.py"
    )
    target = tmp_path / path
    target.write_bytes(
        b"activation_status: ACTIVE\n"
        if mutation == "active"
        else target.read_bytes() + b"TEST_ONLY later content\n"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "TEST_ONLY later commit")
    head = git(tmp_path, "rev-parse", "HEAD")
    if mutation in ("commit", "active"):
        activation["adoption_commit"] = head
        cast("dict[str, str]", activation["candidate_files"])[path] = _hash(
            target.read_bytes()
        )
    elif mutation == "content":
        cast("dict[str, str]", activation["candidate_files"])[path] = _hash(
            target.read_bytes()
        )
    elif mutation == "patch":
        patch = tmp_path / str(activation["adoption_patch_ref"])
        patch.write_bytes(patch.read_bytes() + b"TEST_ONLY changed patch\n")
        activation["adoption_patch_sha256"] = _hash(patch.read_bytes())
    elif mutation in ("subject", "review_head"):
        relative = str(activation["frozen_gate_ref"])
        frozen = json.loads((tmp_path / relative).read_text())
        if mutation == "subject":
            frozen["subject_digest"]["subject_id"] = "0" * 64
            activation["adoption_subject_id"] = "0" * 64
        else:
            frozen["change_set"]["review_head_commit"] = head
        activation["frozen_gate_sha256"] = _write_json(tmp_path, relative, frozen)
    if mutation == "none":
        sole_owner._verify_adoption(tmp_path, activation, datetime.now(UTC))
        assert adopted != head
    else:
        with pytest.raises(ValueError, match=r"COMMITTED_REVIEW_|SOLE_OWNER_"):
            sole_owner._verify_adoption(tmp_path, activation, datetime.now(UTC))


def test_loader_requires_initial_activation_receipt(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    activation.pop("activation_acceptance")
    _write_json(
        root, "runtime/artifacts/governance/TEST_ONLY_activation.json", activation
    )
    with pytest.raises(ValueError, match="activation_acceptance"):
        load_sole_owner_policy(root)


def test_initial_activation_receipt_time_must_follow_adoption(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    cast("dict[str, object]", activation["activation_acceptance"])[
        "accepted_at_utc"
    ] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _write_json(
        root, "runtime/artifacts/governance/TEST_ONLY_activation.json", activation
    )
    with pytest.raises(ValueError, match="SOLE_OWNER_INITIAL_ACTIVATION_TIME_INVALID"):
        load_sole_owner_policy(root)


def _real_git_transition(
    root: Path, phase: str, *, founding: bool = False
) -> tuple[dict[str, object], str]:
    """Real Git/schema/parser lineage with explicitly fabricated TEST_ONLY decisions."""
    from ai4binance.governance import gate as gate_module
    from tests.test_governance_gate import _git_for_committed_review as git

    activation = _real_git_adoption(root, founding=founding)
    activation.update(
        contract_version="SoleHumanOwnerActivation/v2",
        status="ACTIVE",
        repository_root=root.resolve().as_posix(),
        owner_person_id="Huseyin Cicek",
        owner_principal_id="TEST_ONLY_0",
        owner_roles=["GovernanceOwner", "ConstitutionOwner"],
        ownership_duration="PERMANENT_UNTIL_REVOKED_OR_SUPERSEDED",
        adoption_accepted_at_utc=(
            datetime.now(UTC) if founding else datetime.now(UTC) - timedelta(minutes=2)
        ).isoformat(),
        revoked_at_utc=None,
        independent_human_review=False,
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    for step in ["initial"] if phase == "initial" else ["initial", "successor"]:
        base = git(root, "rev-parse", "HEAD")
        prior = (
            load_sole_owner_policy(root, policy_commit=base)
            if step == "successor"
            else None
        )
        activation_ref = (
            f"runtime/artifacts/governance/TEST_ONLY_{step}_activation.json"
        )
        policy = yaml.safe_load((root / POLICY_PATH).read_text())
        policy.update(
            activation_status="ACTIVE",
            owner_principal_id="TEST_ONLY_0",
            activation_record=activation_ref,
        )
        (root / POLICY_PATH).write_text(yaml.safe_dump(policy), encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "TEST_ONLY " + step)
        accepted = git(root, "rev-parse", "HEAD")
        change = gate_module.resolve_committed_governance_change_set(
            root, base, accepted
        )
        subject = gate_module._build_governance_subject_digest(
            root, change
        ).to_payload()
        previous_subject = (
            activation["adoption_subject_id"]
            if step == "initial"
            else cast("dict[str, object]", activation["activation_acceptance"])[
                "subject_id"
            ]
        )
        assert subject["subject_id"] != previous_subject
        gate_ref = (
            f"runtime/artifacts/quality/gate/runs/TEST_ONLY_REAL_{step}/"
            "governance-gate-approval-required.json"
        )
        frozen = {
            "status": "RUNNING_WITH_BLOCKERS",
            "blockers": ["APPROVAL_REQUIRED"],
            "change_set": change.to_payload(),
            "subject_digest": subject,
            "approval_verification": {
                "required_approval_count": 2
                if step == "initial" and not founding
                else 1,
                "approval_profile": "INITIAL_OWNER_AMENDMENT"
                if step == "initial" and founding
                else "LEGACY_C3"
                if step == "initial"
                else "SOLE_HUMAN_OWNER",
            },
            "gate_evidence_sha256": "4" * 64,
            "deterministic_quality_gate": {
                "status": "PASS",
                "gate_evidence_sha256": "3" * 64,
            },
            **{
                key: {"status": "PASS"}
                for key in (
                    "repository_hygiene",
                    "constitution_sync",
                    "repository_conformance",
                    "repository_validator_gate",
                )
            },
        }
        roles = (
            ["GovernanceOwner", "ConstitutionOwner"]
            if step == "initial" and not founding
            else ["GovernanceOwner"]
        )
        records: list[dict[str, object]] = []
        for number, role in enumerate(roles):
            record: dict[str, object] = {
                "approval_id": f"TEST_ONLY_{step}_{number}",
                "approver_id": f"TEST_ONLY_{number}",
                "principal_id": f"TEST_ONLY_{number}",
                "approver_role": role,
                "subject_ref": gate_ref,
                "status": "APPROVED_FOR_IMPLEMENTATION",
                "evidence_refs": ["TEST_ONLY_EVIDENCE"],
                "change_class": "C3_GOVERNED",
                "subject_sha256": subject["subject_id"],
                "scope_hash": change.change_set_sha256,
                "quality_gate_evidence_sha256": "3" * 64,
                "governance_gate_evidence_sha256": "4" * 64,
                "evidence_hash": "5" * 64,
                "authority_family_sha256": subject["authority_family_sha256"],
                "lifecycle_definition_sha256": "7" * 64,
                "approved_at_utc": datetime.now(UTC).isoformat(),
                "expires_at_utc": (
                    datetime.now(UTC) + timedelta(minutes=30)
                ).isoformat(),
            }
            if prior is not None:
                record["sole_owner_confirmation"] = asdict(
                    SoleOwnerConfirmation(
                        prior.owner_person_id,
                        prior.owner_principal_id,
                        prior.policy_sha256,
                        prior.activation_sha256,
                    )
                )
            records.append(record)
        approval_ref = f"runtime/artifacts/governance/TEST_ONLY_{step}_approvals.json"
        receipt = {
            "base_commit": base,
            "accepted_commit": accepted,
            "candidate_files": {POLICY_PATH: _hash((root / POLICY_PATH).read_bytes())},
            "frozen_gate_ref": gate_ref,
            "frozen_gate_sha256": _write_json(root, gate_ref, frozen),
            "approval_records_ref": approval_ref,
            "approval_records_sha256": _write_json(
                root, approval_ref, {"approval_records": records}
            ),
            "subject_id": subject["subject_id"],
            "scope_hash": change.change_set_sha256,
            "quality_sha256": "3" * 64,
            "governance_sha256": "4" * 64,
            "evidence_hash": "5" * 64,
            "authority_family_sha256": subject["authority_family_sha256"],
            "lifecycle_definition_sha256": "7" * 64,
        }
        issued = datetime.now(UTC).isoformat()
        if step == "initial":
            receipt["accepted_at_utc"] = issued
            if founding:
                receipt["initial_amendment"] = _test_only_initial_amendment(
                    root, activation, receipt=receipt
                )
                records[0]["evidence_refs"] = [
                    "runtime/artifacts/governance/TEST_ONLY_ACTIVATION_decision.json"
                ]
                receipt["approval_records_sha256"] = _write_json(
                    root, approval_ref, {"approval_records": records}
                )
                issued = datetime.now(UTC).isoformat()
                receipt["accepted_at_utc"] = issued
        activation[
            "activation_acceptance" if step == "initial" else "successor_acceptance"
        ] = receipt
        activation["issued_at_utc"] = issued
        activation["policy_sha256"] = _hash((root / POLICY_PATH).read_bytes())
        _write_json(root, activation_ref, activation)
    return activation, activation_ref


@pytest.mark.parametrize("phase", ["initial", "successor"])
@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "commit_content",
        "old_subject",
        "old_patch",
        "approval_replay",
        "missing_review",
    ],
)
def test_real_git_transition_binding(tmp_path: Path, phase: str, mutation: str) -> None:
    """Exercise the full policy loader/schema and real parser; no consumer mocks."""
    from ai4binance.governance import gate as gate_module
    from tests.test_governance_gate import _git_for_committed_review as git

    activation, activation_ref = _real_git_transition(tmp_path, phase)
    selected = load_sole_owner_policy(
        tmp_path, policy_commit=git(tmp_path, "rev-parse", "HEAD")
    )
    assert selected is not None
    if mutation == "none":
        assert selected.owner_principal_id == "TEST_ONLY_0"
        return
    key = "activation_acceptance" if phase == "initial" else "successor_acceptance"
    receipt = cast("dict[str, object]", activation[key])
    gate_ref = str(receipt["frozen_gate_ref"])
    frozen = json.loads((tmp_path / gate_ref).read_text())
    approval_path = tmp_path / str(receipt["approval_records_ref"])
    original_approvals = approval_path.read_bytes()
    old_patch = frozen["change_set"]["review_patch_sha256"]
    policy_path = tmp_path / POLICY_PATH
    policy_path.write_bytes(
        policy_path.read_bytes() + b"# TEST_ONLY unreviewed content\n"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "TEST_ONLY unreviewed target")
    head = git(tmp_path, "rev-parse", "HEAD")
    receipt["accepted_commit"] = head
    receipt["candidate_files"] = {POLICY_PATH: _hash(policy_path.read_bytes())}
    activation["policy_sha256"] = _hash(policy_path.read_bytes())
    if mutation == "commit_content":
        frozen["change_set"]["review_head_commit"] = head
        frozen["change_set"]["git_commit"] = head
    else:
        change = gate_module.resolve_committed_governance_change_set(
            tmp_path, str(receipt["base_commit"]), head
        )
        frozen["change_set"] = change.to_payload()
        if mutation == "old_patch":
            frozen["change_set"]["review_patch_sha256"] = old_patch
        if mutation == "missing_review":
            frozen["change_set"].pop("review_patch_sha256")
        if mutation == "approval_replay":
            subject = gate_module._build_governance_subject_digest(
                tmp_path, change
            ).to_payload()
            frozen["subject_digest"] = subject
            receipt["subject_id"] = subject["subject_id"]
            receipt["scope_hash"] = change.change_set_sha256
    receipt["frozen_gate_sha256"] = _write_json(tmp_path, gate_ref, frozen)
    _write_json(tmp_path, activation_ref, activation)
    assert approval_path.read_bytes() == original_approvals
    with pytest.raises(
        ValueError, match=r"COMMITTED_REVIEW_|SOLE_OWNER_.*APPROVAL_INVALID"
    ):
        load_sole_owner_policy(tmp_path, policy_commit=head)


def _write_json(root: Path, relative: str, value: object) -> str:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value), encoding="utf-8")
    return _hash(target.read_bytes())


def _synthetic_activation(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], dict[str, bytes]]:
    """Exercise all four phases using test-only Git facts and approval records."""
    from ai4binance.governance import gate as gate_module
    from ai4binance.governance import sole_owner

    now = datetime.now(UTC)
    base, adopted, head = "a" * 40, "b" * 40, "c" * 40
    candidate_bytes = {
        path: f"TEST_ONLY_CANDIDATE:{path}".encode() for path in MODEL_CONTROL_PATHS
    }
    accepted_policy_bytes = b""
    inactive_policy_bytes = (root / POLICY_PATH).read_bytes()

    def git_fact(_root: Path, *args: str) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return (head + "\n").encode()
        if args[:2] == ("merge-base", "--is-ancestor"):
            if args[2:] in (
                (base, adopted),
                (adopted, head),
                (base, head),
                (adopted, adopted),
                (head, head),
            ):
                return b""
        if args[:3] == ("diff", "--name-only", "--no-renames"):
            if args[3:] == (base, adopted):
                return ("\n".join(sorted(candidate_bytes)) + "\n").encode()
            if args[3:] == (adopted, head):
                return (POLICY_PATH + "\n").encode()
        if args[:1] == ("ls-tree",):
            if args[2:] == (head, "--", POLICY_PATH):
                return (POLICY_PATH + "\n").encode()
        if args[:1] == ("show",):
            commit, _, path = args[1].partition(":")
            if commit == head and path == POLICY_PATH:
                return accepted_policy_bytes
            if commit == head and path == SCHEMA_PATH:
                return (root / SCHEMA_PATH).read_bytes()
            if commit == adopted and path in candidate_bytes:
                return candidate_bytes[path]
        raise ValueError("SOLE_OWNER_ADOPTION_GIT_BINDING")

    monkeypatch.setattr(sole_owner, "_git", git_fact)
    original_change_set = _change_set
    monkeypatch.setattr(
        sys.modules[__name__],
        "_change_set",
        lambda repository, path: replace(
            original_change_set(repository, path), git_commit=head, change_set_sha256=""
        ),
    )
    policy_path = root / POLICY_PATH
    policy_data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy_data.update(
        activation_status="ACTIVE",
        activation_record="runtime/artifacts/governance/TEST_ONLY_activation.json",
        owner_principal_id="TEST_ONLY_A",
    )
    policy_path.write_text(yaml.safe_dump(policy_data), encoding="utf-8")
    accepted_policy_bytes = policy_path.read_bytes()
    candidate_bytes[POLICY_PATH] = inactive_policy_bytes
    patch_ref = "runtime/artifacts/governance/TEST_ONLY_patch.txt"
    patch_path = root / patch_ref
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(b"TEST_ONLY_REVIEW_PATCH")
    change = gate_module.GovernanceChangeSet(
        root.resolve(),
        adopted,
        changed_paths=tuple(sorted(candidate_bytes)),
        review_base_commit=base,
        review_head_commit=adopted,
        review_patch_sha256=_hash(patch_path.read_bytes()),
    )
    initial_change = gate_module.GovernanceChangeSet(
        root.resolve(),
        head,
        changed_paths=(POLICY_PATH,),
        review_base_commit=adopted,
        review_head_commit=head,
        review_patch_sha256=_hash(b"TEST_ONLY_INITIAL_ACTIVATION_DIFF"),
    )

    def test_only_resolver(
        repository: Path,
        review_base: str,
        review_head: str,
        *,
        historical: bool = False,
    ) -> GovernanceChangeSet:
        assert repository == root
        assert historical
        if (review_base, review_head) == (base, adopted):
            return change
        if (review_base, review_head) == (adopted, head):
            return initial_change
        raise ValueError("TEST_ONLY_CANONICAL_REVIEW_TARGET_DRIFT")

    monkeypatch.setattr(
        gate_module, "_resolve_committed_change_set", test_only_resolver
    )
    subject_payload = gate_module._build_governance_subject_digest(
        root, change
    ).to_payload()
    subject, scope = str(subject_payload["subject_id"]), change.change_set_sha256
    quality, governance, evidence = "3" * 64, "4" * 64, "5" * 64
    authority, lifecycle = "6" * 64, "7" * 64
    frozen_ref = (
        "runtime/artifacts/quality/gate/runs/TEST_ONLY/"
        "governance-gate-approval-required.json"
    )
    frozen = {
        "status": "RUNNING_WITH_BLOCKERS",
        "blockers": ["APPROVAL_REQUIRED"],
        "gate_evidence_sha256": governance,
        "approval_verification": {
            "required_approval_count": 2,
            "approval_profile": "LEGACY_C3",
        },
        "subject_digest": subject_payload,
        "change_set": change.to_payload(),
        "deterministic_quality_gate": {
            "status": "PASS",
            "gate_evidence_sha256": quality,
        },
        "repository_hygiene": {"status": "PASS"},
        "constitution_sync": {"status": "PASS"},
        "repository_conformance": {"status": "PASS"},
        "repository_validator_gate": {"status": "PASS"},
    }
    frozen_sha = _write_json(root, frozen_ref, frozen)
    approved_at = (now - timedelta(minutes=10)).isoformat()
    expires_at = (now + timedelta(minutes=30)).isoformat()
    records = [
        {
            "approval_id": f"TEST_ONLY_APPROVAL_{index}",
            "approver_id": principal,
            "principal_id": principal,
            "approver_role": role,
            "subject_ref": frozen_ref,
            "status": "APPROVED_FOR_IMPLEMENTATION",
            "evidence_refs": ["TEST_ONLY_EVIDENCE"],
            "change_class": "C3_GOVERNED",
            "subject_sha256": subject,
            "scope_hash": scope,
            "quality_gate_evidence_sha256": quality,
            "governance_gate_evidence_sha256": governance,
            "evidence_hash": evidence,
            "authority_family_sha256": authority,
            "lifecycle_definition_sha256": lifecycle,
            "approved_at_utc": approved_at,
            "expires_at_utc": expires_at,
        }
        for index, (principal, role) in enumerate(
            (
                ("TEST_ONLY_A", "GovernanceOwner"),
                ("TEST_ONLY_B", "ConstitutionOwner"),
            )
        )
    ]
    approvals_ref = "runtime/artifacts/governance/TEST_ONLY_transition_records.json"
    approvals_sha = _write_json(root, approvals_ref, {"approval_records": records})
    activation: dict[str, object] = {
        "contract_version": "SoleHumanOwnerActivation/v2",
        "status": "ACTIVE",
        "repository_root": root.resolve().as_posix(),
        "policy_sha256": _hash(policy_path.read_bytes()),
        "owner_person_id": "Huseyin Cicek",
        "owner_principal_id": "TEST_ONLY_A",
        "owner_roles": ["GovernanceOwner", "ConstitutionOwner"],
        "adoption_base_commit": base,
        "adoption_commit": adopted,
        "adoption_patch_ref": patch_ref,
        "adoption_patch_sha256": _hash(patch_path.read_bytes()),
        "adoption_subject_id": subject,
        "adoption_scope_hash": scope,
        "adoption_quality_sha256": quality,
        "adoption_governance_sha256": governance,
        "adoption_evidence_hash": evidence,
        "adoption_authority_family_sha256": authority,
        "adoption_lifecycle_sha256": lifecycle,
        "frozen_gate_ref": frozen_ref,
        "frozen_gate_sha256": frozen_sha,
        "approval_records_ref": approvals_ref,
        "approval_records_sha256": approvals_sha,
        "candidate_files": {
            path: _hash(data) for path, data in candidate_bytes.items()
        },
        "issued_at_utc": (now - timedelta(minutes=5)).isoformat(),
        "ownership_duration": "PERMANENT_UNTIL_REVOKED_OR_SUPERSEDED",
        "adoption_accepted_at_utc": (now - timedelta(minutes=5)).isoformat(),
        "revoked_at_utc": None,
        "independent_human_review": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    initial_ref = frozen_ref.replace("TEST_ONLY/", "TEST_ONLY_INITIAL/")
    initial_gate = dict(frozen)
    initial_subject = gate_module._build_governance_subject_digest(
        root, initial_change
    ).to_payload()
    initial_gate["change_set"] = initial_change.to_payload()
    initial_gate["subject_digest"] = initial_subject
    assert initial_subject["subject_id"] != subject
    initial_sha = _write_json(root, initial_ref, initial_gate)
    initial_approval_ref = approvals_ref.replace("transition", "initial")
    initial_records = [
        dict(
            record,
            subject_ref=initial_ref,
            subject_sha256=initial_subject["subject_id"],
            scope_hash=initial_change.change_set_sha256,
        )
        for record in records
    ]
    initial_approval_sha = _write_json(
        root, initial_approval_ref, {"approval_records": initial_records}
    )
    activation["activation_acceptance"] = {
        "accepted_at_utc": activation["issued_at_utc"],
        "base_commit": adopted,
        "accepted_commit": head,
        "candidate_files": {POLICY_PATH: _hash(accepted_policy_bytes)},
        "frozen_gate_ref": initial_ref,
        "frozen_gate_sha256": initial_sha,
        "approval_records_ref": initial_approval_ref,
        "approval_records_sha256": initial_approval_sha,
        "subject_id": initial_subject["subject_id"],
        "scope_hash": initial_change.change_set_sha256,
        "quality_sha256": quality,
        "governance_sha256": governance,
        "evidence_hash": evidence,
        "authority_family_sha256": authority,
        "lifecycle_definition_sha256": lifecycle,
    }
    _write_json(root, policy_data["activation_record"], activation)
    return activation, candidate_bytes


def test_synthetic_transition_activation_and_later_c3(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    selected = load_sole_owner_policy(root)
    assert selected is not None
    assert selected.owner_principal_id == "TEST_ONLY_A"
    report = _report(root, (_record(root, selected),))
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert report.approval_verification.required_approval_count == 1
    assert activation["adoption_base_commit"] != activation["adoption_commit"]


def test_completed_ownership_survives_adoption_approval_expiry(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synthetic_activation(root, monkeypatch)
    selected = load_sole_owner_policy(root, now=datetime.now(UTC) + timedelta(days=365))
    assert selected is not None
    assert selected.owner_principal_id == "TEST_ONLY_A"


def test_revoked_owner_authority_remains_denied(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    activation["revoked_at_utc"] = datetime.now(UTC).isoformat()
    _write_json(
        root, "runtime/artifacts/governance/TEST_ONLY_activation.json", activation
    )
    with pytest.raises(ValueError, match="SOLE_OWNER_AUTHORITY_REVOKED"):
        load_sole_owner_policy(root)


def test_initial_approval_must_be_valid_at_adoption_acceptance(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    activation["adoption_accepted_at_utc"] = (
        datetime.now(UTC) + timedelta(hours=1)
    ).isoformat()
    activation["issued_at_utc"] = activation["adoption_accepted_at_utc"]
    _write_json(
        root, "runtime/artifacts/governance/TEST_ONLY_activation.json", activation
    )
    with pytest.raises(ValueError, match="SOLE_OWNER_TRANSITION_APPROVAL_INVALID"):
        load_sole_owner_policy(root, now=datetime.now(UTC) + timedelta(hours=2))


def test_accepted_schema_never_resolves_network_references(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synthetic_activation(root, monkeypatch)
    schema_path = root / SCHEMA_PATH
    schema = json.loads(schema_path.read_text())
    schema["$defs"]["policy"]["properties"]["profile"] = {
        "$ref": "https://example.invalid/unauthorized-schema"
    }
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="network schema reference is forbidden"):
        load_sole_owner_policy(root, policy_commit="c" * 40)


def test_successor_policy_bytes_cannot_authorize_own_review(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synthetic_activation(root, monkeypatch)
    accepted = load_sole_owner_policy(root, policy_commit="c" * 40)
    assert accepted is not None
    policy_path = root / POLICY_PATH
    policy_path.write_text("activation_status: INACTIVE\n", encoding="utf-8")
    selected = load_sole_owner_policy(root, policy_commit="c" * 40)
    assert selected == accepted
    record = _record(root, selected, path=POLICY_PATH)
    report = _report(root, (record,), path=POLICY_PATH)
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    assert report.approval_verification.required_approval_count == 1


def test_unaccepted_successor_cannot_be_activated(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    path = root / POLICY_PATH
    path.write_bytes(path.read_bytes() + b"# TEST_ONLY successor\n")
    activation["policy_sha256"] = _hash(path.read_bytes())
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    _write_json(root, data["activation_record"], activation)
    from ai4binance.governance import sole_owner

    original_git = sole_owner._git

    def successor_git(_root: Path, *args: str) -> bytes:
        if args == ("show", "c" * 40 + ":" + POLICY_PATH):
            return path.read_bytes()
        return original_git(_root, *args)

    monkeypatch.setattr(sole_owner, "_git", successor_git)
    with pytest.raises(ValueError, match="SOLE_OWNER_INITIAL_ACTIVATION_BYTES_DRIFT"):
        load_sole_owner_policy(root, policy_commit="c" * 40)


@pytest.mark.parametrize(
    "field",
    [
        "adoption_base_commit",
        "adoption_scope_hash",
        "adoption_patch_sha256",
        "frozen_gate_sha256",
        "approval_records_sha256",
    ],
)
def test_synthetic_transition_rejects_stale_or_changed_evidence(
    root: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    activation[field] = "0" * (40 if field == "adoption_base_commit" else 64)
    policy_data = yaml.safe_load((root / POLICY_PATH).read_text(encoding="utf-8"))
    _write_json(root, policy_data["activation_record"], activation)
    with pytest.raises(ValueError, match="SOLE_OWNER_"):
        load_sole_owner_policy(root)


def test_synthetic_transition_rejects_candidate_byte_drift(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activation, _ = _synthetic_activation(root, monkeypatch)
    files = dict(cast("dict[str, str]", activation["candidate_files"]))
    files[POLICY_PATH] = "0" * 64
    activation["candidate_files"] = files
    policy_data = yaml.safe_load((root / POLICY_PATH).read_text(encoding="utf-8"))
    _write_json(root, policy_data["activation_record"], activation)
    with pytest.raises(ValueError, match="SOLE_OWNER_ADOPTION_BYTES_DRIFT"):
        load_sole_owner_policy(root)


@pytest.mark.parametrize("phase", ["PERMANENT", "ADOPTION", "ACTIVATION"])
def test_closure_request_uses_one_owner_and_required_constitution_role(
    root: Path, policy: SoleOwnerPolicy, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    monkeypatch.setattr(
        sys.modules["ai4binance.governance.sole_owner"],
        "load_sole_owner_policy",
        lambda _root, policy_commit=None: policy,
    )
    source = CANDIDATE / "scripts/prepare_c3_human_governance_closure_request.py"
    spec = importlib.util.spec_from_file_location("TEST_ONLY_closure_request", source)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    gate_path = root / "runtime/artifacts/quality/gate/TEST_ONLY_gate.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        json.dumps(
            {
                "gate_evidence_sha256": "1" * 64,
                "change_set": {
                    "git_commit": "a" * 40,
                    "changed_paths": [POLICY_PATH]
                    if phase == "ACTIVATION"
                    else ["docs/governance/framework_core_vnext_governance.md"],
                    "change_set_sha256": "2" * 64,
                },
                "subject_digest": {
                    "subject_id": "3" * 64,
                    "authority_family_sha256": "4" * 64,
                },
                "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
                "authority_baseline": {"authority_sources": []},
                "approval_verification": {
                    "change_class": "C3_GOVERNED",
                    "required_approval_count": 1,
                    "approval_profile": "SOLE_HUMAN_OWNER"
                    if phase == "PERMANENT"
                    else "INITIAL_OWNER_AMENDMENT",
                    "evidence_hash": "6" * 64,
                    "authority_family_sha256": "4" * 64,
                    "lifecycle_definition_sha256": "7" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    packet = module.build_closure_request(
        repository_root=root, governance_gate_report_path=gate_path
    )
    assert packet["approval_status"] == "DRAFT_ONLY_NOT_APPROVAL"
    assert packet["required_roles"] == (
        ["GovernanceOwner"] if phase == "ACTIVATION" else ["ConstitutionOwner"]
    )
    assert packet["independent_human_review"] is False
    assert packet["required_human_person_count"] == 1
    template = packet["approval_record_template"]
    assert len(template) == 1
    assert template[0]["status"] == "DRAFT_ONLY_NOT_APPROVAL"
    if phase == "PERMANENT":
        assert template[0]["principal_id"] == policy.owner_principal_id
        assert (
            template[0]["sole_owner_confirmation"]["policy_sha256"]
            == policy.policy_sha256
        )
    else:
        assert template[0]["principal_id"] == "<registered-owner-principal>"
        assert "sole_owner_confirmation" not in template[0]
        assert all(
            "independent" not in line.lower() or "without" in line.lower()
            for line in packet["instructions"]
        )


def test_real_successor_requires_predecessor_approval(tmp_path: Path) -> None:
    activation, activation_ref = _real_git_transition(tmp_path, "successor")
    receipt = cast("dict[str, object]", activation["successor_acceptance"])
    relative = str(receipt["approval_records_ref"])
    records = json.loads((tmp_path / relative).read_text())
    records["approval_records"][0]["approver_role"] = "TEST_ONLY_UNAUTHORIZED"
    receipt["approval_records_sha256"] = _write_json(tmp_path, relative, records)
    _write_json(tmp_path, activation_ref, activation)
    with pytest.raises(ValueError, match="SOLE_OWNER_SUCCESSOR_APPROVAL_INVALID"):
        load_sole_owner_policy(tmp_path)


def test_real_first_activation_requires_legacy_two_people(tmp_path: Path) -> None:
    activation, activation_ref = _real_git_transition(tmp_path, "initial")
    receipt = cast("dict[str, object]", activation["activation_acceptance"])
    relative = str(receipt["approval_records_ref"])
    records = json.loads((tmp_path / relative).read_text())
    records["approval_records"] = records["approval_records"][:1]
    receipt["approval_records_sha256"] = _write_json(tmp_path, relative, records)
    _write_json(tmp_path, activation_ref, activation)
    with pytest.raises(
        ValueError, match="SOLE_OWNER_INITIAL_ACTIVATION_TWO_PEOPLE_REQUIRED"
    ):
        load_sole_owner_policy(tmp_path)

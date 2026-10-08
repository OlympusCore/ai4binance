"""TEST_ONLY: candidate contracts; mocked installation never proves live authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai4binance.enterprise.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    WorkflowIdentity,
)
from ai4binance.governance import gate
from ai4binance.governance import package_owner_acceptance as owner
from ai4binance.governance.document_lock_authority import CONTEXT_PATH
from ai4binance.governance.framework import ChangeApprovalClass
from ai4binance.governance.governance_enforcement_fabric import FABRIC_PATH
from ai4binance.schema_validation import (
    SchemaValidationError,
    validate_local_definition,
)
from tests.test_governance_constitution_sync import (
    write_core_documents,
    write_quality_evidence,
)

NOW = datetime(2026, 10, 7, 16, tzinfo=UTC)


def _review_payload(relative: str) -> bytes:
    return (Path(__file__).resolve().parents[1] / relative).read_bytes()


def _write(root: Path, relative: str, value: object) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value) + "\n").encode()
    path.write_bytes(raw)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """TEST_ONLY sealed inputs; canonical installation verification is substituted."""
    _write(
        tmp_path,
        "schemas/governance/governance_enforcement_fabric.schema.json",
        _review_payload("schemas/governance/governance_enforcement_fabric.schema.json"),
    )
    fabric = yaml.safe_load(
        _review_payload("config/governance/governance_enforcement_fabric.yaml").decode(
            "utf-8"
        )
    )
    policy = fabric["bounded_owner_acceptance"]
    policy["canonical_root"] = tmp_path.as_posix()
    policy["allowed_change_paths"] = [
        owner.CORE,
        FABRIC_PATH.as_posix(),
        "tests/test_package.py",
        "0",
    ]
    policy["reviewed_output_paths"] = [
        owner.CORE,
        FABRIC_PATH.as_posix(),
        "tests/test_package.py",
    ]
    core = _write(tmp_path, owner.CORE, b"TEST_ONLY AI4B-GOV-C3-OWNER-20261007\n")
    policy["core_sha256"] = core["sha256"]
    policy["package_patch_sha256"] = hashlib.sha256(
        b"TEST_ONLY_ORIGINAL_PATCH"
    ).hexdigest()
    _write(tmp_path, "tests/test_package.py", b"# TEST_ONLY payload\n")
    _write(tmp_path, FABRIC_PATH.as_posix(), yaml.safe_dump(fabric).encode())
    outputs = {
        p: hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()
        for p in policy["reviewed_output_paths"]
    }
    evidence = _write(
        tmp_path,
        "runtime/artifacts/TEST_ONLY/evidence.json",
        {"artifact_origin": "TEST_ONLY", "reviewed_output_hashes": outputs},
    )
    source = _write(
        tmp_path,
        "runtime/artifacts/TEST_ONLY/owner.raw.txt",
        b"TEST_ONLY normative decision; no actual person or approval\n",
    )
    grant = _write(
        tmp_path,
        "runtime/artifacts/TEST_ONLY/grant.json",
        {
            "source": source,
            "issued_at_utc": (NOW - timedelta(minutes=1)).isoformat(),
            "expires_at_utc": (NOW + timedelta(hours=1)).isoformat(),
            "review_subject": {
                "epoch_id": policy["epoch_id"],
                "evidence": evidence,
                "baseline_commit": policy["review_baseline_commit"],
                "documents": [
                    {
                        "path": owner.CORE,
                        "before_sha256": owner.PRIOR_CORE_SHA256,
                        "before_version": "2.0.13",
                        "version": "2.0.14",
                        "sha256": policy["core_sha256"],
                    }
                ],
            },
        },
    )
    context = {
        "contract_version": "DocumentLockAuthorityContext/v4",
        "repository_root": tmp_path.as_posix(),
        "grant": grant,
        "subject_sha256": "1" * 64,
        "owner_person_id": policy["owner_person_id"],
        "predecessor": evidence,
        "final_manifest": evidence,
        "completion": evidence,
        "revocations": evidence,
    }
    _write(tmp_path, CONTEXT_PATH, context)
    _write(tmp_path, owner.MANIFEST, {"artifact_origin": "TEST_ONLY"})
    decision = {
        "contract_version": "BoundedOwnerNormativeAmendment/v1",
        "rule_id": owner.RULE,
        "record_origin": "OWNER_ISSUED",
        "status": "ISSUED",
        "decision": "RECOGNIZE_EXACT_OWNER_PACKAGE_ACCEPTANCE",
        "owner_person_id": policy["owner_person_id"],
        "grant": grant,
        "source": source,
        "subject_sha256": "1" * 64,
        "issued_at_utc": NOW.isoformat(),
        "expires_at_utc": (NOW + timedelta(minutes=50)).isoformat(),
        "revoked_at_utc": None,
        "human_confirmation": True,
        "natural_person_count": 1,
        "independent_human_review": False,
        "departure_from_legacy_c3": True,
        "previous_c3_approval": False,
        "historical_approval_gaps_closed": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    _write(tmp_path, policy["normative_decision_ref"], decision)
    monkeypatch.setattr(
        owner, "prospective_document_approvals", lambda *_: (frozenset(), None)
    )
    monkeypatch.setattr(
        owner,
        "read_verified_governed_document",
        lambda *_: (tmp_path / owner.CORE).read_text(),
    )
    monkeypatch.setattr(
        owner,
        "_git",
        lambda _root, *args: b"TEST_ONLY_ORIGINAL_PATCH" if args[0] == "diff" else b"",
    )
    change_set = gate.GovernanceChangeSet(
        tmp_path, "a" * 40, changed_paths=("tests/test_package.py",)
    )
    return {
        "root": tmp_path,
        "policy": policy,
        "decision": decision,
        "context": context,
        "change_set": change_set,
    }


def test_fixture_uses_canonical_v4_context_contract(package: dict[str, Any]) -> None:
    """TEST_ONLY references; structural fidelity prevents invented context fields."""
    schema_path = (
        package["root"] / "schemas/governance/document_lock_authority.schema.json"
    )
    schema_path.write_bytes(
        _review_payload("schemas/governance/document_lock_authority.schema.json")
    )
    validate_local_definition(schema_path, "update_context", package["context"])
    assert "epoch_id" not in package["context"]


def test_missing_projection_preserves_legacy_defaults(tmp_path: Path) -> None:
    scope = gate.GovernanceChangeSet(tmp_path, "a" * 40, changed_paths=("tests/x.py",))
    assert (
        owner.load_package_owner_acceptance(
            tmp_path, scope.changed_paths, "C3_GOVERNED", now=NOW
        )
        is None
    )
    assert gate._approval_requirements(ChangeApprovalClass.C3_GOVERNED)[0] == 2


def test_only_eligible_test_package_recognized(package: dict[str, Any]) -> None:
    policy = owner.load_package_owner_acceptance(
        package["root"], package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
    )
    assert policy is not None
    assert policy.principal_id == "huseyin-governance-owner-principal"
    assert (
        owner.load_package_owner_acceptance(
            package["root"],
            package["change_set"].changed_paths,
            "C4_CONSEQUENTIAL",
            now=NOW,
        )
        is None
    )
    other = replace(
        package["change_set"],
        changed_paths=("src/unreviewed.py",),
        change_set_sha256="",
    )
    assert (
        owner.load_package_owner_acceptance(
            package["root"], other.changed_paths, "C3_GOVERNED", now=NOW
        )
        is None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "DRAFT"),
        ("record_origin", "CODEX"),
        ("departure_from_legacy_c3", False),
        ("independent_human_review", True),
        ("natural_person_count", 2),
        ("execution_allowed", True),
        ("historical_approval_gaps_closed", True),
    ],
)
def test_false_authority_claims_rejected(
    package: dict[str, Any], field: str, value: object
) -> None:
    decision = {**package["decision"], field: value}
    _write(package["root"], package["policy"]["normative_decision_ref"], decision)
    with pytest.raises(SchemaValidationError):
        owner.load_package_owner_acceptance(
            package["root"], package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "revoked",
        "future",
        "too_long",
        "wrong_subject",
        "wrong_source",
        "wrong_epoch",
        "output_drift",
        "missing_output",
        "recreated_deleted_path",
        "core_drift",
        "bad_original_patch",
        "missing_decision",
    ],
)
def test_independent_vetoes(
    package: dict[str, Any], mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, policy = package["root"], package["policy"]
    decision = dict(package["decision"])
    if mutation == "expired":
        decision["expires_at_utc"] = (NOW - timedelta(seconds=1)).isoformat()
    if mutation == "revoked":
        decision["revoked_at_utc"] = NOW.isoformat()
    if mutation == "future":
        decision["issued_at_utc"] = (NOW + timedelta(seconds=1)).isoformat()
    if mutation == "too_long":
        decision["expires_at_utc"] = (NOW + timedelta(days=2)).isoformat()
    if mutation == "wrong_subject":
        decision["subject_sha256"] = "2" * 64
    if mutation == "wrong_source":
        decision["source"] = {**decision["source"], "sha256": "0" * 64}
    if mutation == "wrong_epoch":
        context = dict(package["context"])
        grant = json.loads((root / context["grant"]["path"]).read_text())
        grant["review_subject"]["epoch_id"] = "wrong"
        context["grant"] = _write(root, context["grant"]["path"], grant)
        decision["grant"] = context["grant"]
        _write(root, CONTEXT_PATH, context)
    if mutation == "output_drift":
        (root / "tests/test_package.py").write_bytes(b"changed\n")
    if mutation == "missing_output":
        (root / "tests/test_package.py").unlink()
    if mutation == "recreated_deleted_path":
        (root / "0").write_bytes(b"unapproved\n")
    if mutation == "core_drift":
        (root / owner.CORE).write_bytes(b"changed\n")
    if mutation == "bad_original_patch":
        monkeypatch.setattr(owner, "_git", lambda *_: b"changed")
    _write(root, policy["normative_decision_ref"], decision)
    if mutation == "missing_decision":
        (root / policy["normative_decision_ref"]).unlink()
    with pytest.raises((ValueError, OSError)):
        owner.load_package_owner_acceptance(
            root, package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )


def test_actual_installation_verifier_veto_preserved(
    package: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        owner,
        "prospective_document_approvals",
        lambda *_: (frozenset(), "TEST_ONLY original chain veto"),
    )
    with pytest.raises(ValueError, match="INSTALLATION_UNVERIFIED"):
        owner.load_package_owner_acceptance(
            package["root"], package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )


def test_later_successor_cannot_reuse_recognition(package: dict[str, Any]) -> None:
    root = package["root"]
    context = dict(package["context"])
    grant = json.loads((root / context["grant"]["path"]).read_text())
    grant["review_subject"]["documents"][0]["version"] = "2.0.15"
    context["grant"] = _write(root, context["grant"]["path"], grant)
    decision = {**package["decision"], "grant": context["grant"]}
    _write(root, CONTEXT_PATH, context)
    _write(root, package["policy"]["normative_decision_ref"], decision)
    with pytest.raises(ValueError, match="EXACT_AMENDMENT_REQUIRED"):
        owner.load_package_owner_acceptance(
            root, package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )


def _record() -> ApprovalRecord:
    return ApprovalRecord(
        WorkflowIdentity("TEST_ONLY", "TEST_ONLY", "TEST_ONLY", NOW),
        "TEST_ONLY",
        "Huseyin",
        "TEST_ONLY",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("TEST_ONLY",),
        approver_role="GovernanceOwner",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256="1" * 64,
        scope_hash="2" * 64,
        quality_gate_evidence_sha256="3" * 64,
        governance_gate_evidence_sha256="4" * 64,
        evidence_hash="5" * 64,
        authority_family_sha256="6" * 64,
        lifecycle_definition_sha256="7" * 64,
        principal_id="huseyin-governance-owner-principal",
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=20),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"principal_id": "another"},
        {"approver_id": "another"},
        {"approver_role": "ConstitutionOwner"},
        {"expires_at": None},
        {"expires_at": NOW + timedelta(days=1)},
    ],
)
def test_other_identity_or_authority_rejected(changes: dict[str, Any]) -> None:
    policy = owner.PackageOwnerAcceptance(
        "Huseyin Cicek",
        "Huseyin",
        "huseyin-governance-owner-principal",
        "GovernanceOwner",
        NOW + timedelta(hours=1),
    )
    assert not policy.record_blockers(_record())
    assert policy.record_blockers(replace(_record(), **changes))


def test_candidate_gate_single_owner_keeps_scope_veto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import test_governance_gate as fixtures

    write_core_documents(
        tmp_path, compliance_extra="src/ai4binance/governance/framework.py"
    )
    write_quality_evidence(tmp_path)
    (tmp_path / "src/ai4binance/governance").mkdir(parents=True)
    (tmp_path / "src/ai4binance/governance/framework.py").write_text(
        "class Core: ...\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_governance_framework.py").write_text(
        "from ai4binance.governance.framework import Core\n", encoding="utf-8"
    )
    fixtures._stamp_authority_frontmatter(tmp_path)
    change_set = fixtures._change_set(
        tmp_path,
        "src/ai4binance/governance/framework.py",
        "tests/test_governance_framework.py",
    )
    quality = fixtures._quality_report(tmp_path, change_set=change_set)
    owner_policy = owner.PackageOwnerAcceptance(
        "TEST_ONLY",
        "Huseyin",
        "huseyin-governance-owner-principal",
        "GovernanceOwner",
        datetime.now(UTC) + timedelta(hours=1),
    )
    monkeypatch.setattr(gate, "load_package_owner_acceptance", lambda *_: owner_policy)
    kwargs: dict[str, Any] = {
        "repository_root": tmp_path,
        "repository_validator": gate.load_repository_validator_evidence(
            fixtures._write_validator_report(tmp_path)
        ),
        "docs_hygiene": fixtures._docs_hygiene(True),
        "artifact_hygiene": fixtures._artifact_hygiene(True),
        "constitution_sync_tests": fixtures._constitution_sync_tests(True),
        "deterministic_quality_gate": quality,
        "change_set": change_set,
        "require_change_set": True,
    }
    provisional = gate.build_governance_gate_report(**kwargs)
    verified = provisional.approval_verification
    assert verified is not None
    assert provisional.subject_digest is not None
    approved = replace(
        _record(),
        subject_sha256=provisional.subject_digest.subject_id,
        scope_hash=change_set.change_set_sha256,
        change_class=ChangeApprovalClass.C3_GOVERNED,
        quality_gate_evidence_sha256=quality.gate_evidence_sha256,
        governance_gate_evidence_sha256=provisional.gate_evidence_sha256,
        evidence_hash=fixtures._approval_evidence_hash(quality, provisional),
        authority_family_sha256=provisional.subject_digest.authority_family_sha256,
        lifecycle_definition_sha256=fixtures._lifecycle_definition_sha256(),
        approved_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    report = gate.build_governance_gate_report(**kwargs, approval_records=(approved,))
    assert report.approval_verification is not None
    assert report.approval_verification.status is gate.ApprovalVerificationStatus.PASS
    assert report.approval_verification.required_approval_count == 1
    assert report.approval_verification.independent_human_review is False
    assert report.approval_verification.human_person_count == 1
    assert report.approval_verification.hard_veto is True
    invalid = gate.build_governance_gate_report(
        **kwargs, approval_records=(replace(approved, scope_hash="0" * 64),)
    )
    assert invalid.approval_verification is not None
    assert any(
        b.startswith("APPROVAL_SCOPE_MISMATCH")
        for b in invalid.approval_verification.blockers
    )


@pytest.mark.parametrize("profile", ["BOUNDED_OWNER_PACKAGE", "LEGACY_C3"])
def test_closure_uses_actual_human_profile(tmp_path: Path, profile: str) -> None:
    from scripts.prepare_c3_human_governance_closure_request import (
        build_closure_request,
        render_closure_request_markdown,
    )

    verification: dict[str, Any] = {
        "change_class": "C3_GOVERNED",
        "required_approval_count": 2,
        "evidence_hash": "6" * 64,
        "authority_family_sha256": "4" * 64,
        "lifecycle_definition_sha256": "7" * 64,
        "approval_profile": profile,
    }
    if profile == "BOUNDED_OWNER_PACKAGE":
        verification.update(
            required_approval_count=1,
            independent_human_review=False,
            bounded_owner_identity={
                "owner_person_id": "TEST_ONLY",
                "approver_id": "Huseyin",
                "principal_id": "huseyin-governance-owner-principal",
                "approver_role": "GovernanceOwner",
                "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )
    report = {
        "artifact_origin": "TEST_ONLY",
        "gate_evidence_sha256": "1" * 64,
        "change_set": {"change_set_sha256": "2" * 64},
        "subject_digest": {"subject_id": "3" * 64, "authority_family_sha256": "4" * 64},
        "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
        "authority_baseline": {"authority_sources": [owner.CORE]},
        "approval_verification": verification,
    }
    ref = _write(tmp_path, "runtime/artifacts/TEST_ONLY/governance.json", report)
    request = build_closure_request(
        repository_root=tmp_path, governance_gate_report_path=tmp_path / ref["path"]
    )
    if profile == "BOUNDED_OWNER_PACKAGE":
        assert request["required_roles"] == ["GovernanceOwner"]
        assert request["required_approval_count"] == 1
        assert request["independent_human_review"] is False
        assert request["required_human_person_count"] == 1
        assert (
            request["approval_record_template"][0]["principal_id"]
            == "huseyin-governance-owner-principal"
        )
        assert "set-by-independent-approver" not in render_closure_request_markdown(
            request
        )
    else:
        assert request["required_roles"] == ["GovernanceOwner", "ConstitutionOwner"]
        assert request["required_approval_count"] == 2
    assert request["execution_allowed"] is False
    assert request["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_predecessor_grant_cannot_approve_quality_repair_successor(
    package: dict[str, Any],
) -> None:
    """TEST_ONLY old review anchors cannot approve the fresh repair subject."""
    root = package["root"]
    context = dict(package["context"])
    grant = json.loads((root / context["grant"]["path"]).read_text())
    review = grant["review_subject"]
    review["baseline_commit"] = package["policy"]["package_commit"]
    review["documents"][0].update(
        before_version="2.0.11",
        version="2.0.12",
        before_sha256="7147a031c7774e03def1a232030c70af32f110af83898b4f04f43b4c9e8d7e08",
    )
    context["grant"] = _write(root, context["grant"]["path"], grant)
    _write(root, CONTEXT_PATH, context)
    _write(
        root,
        package["policy"]["normative_decision_ref"],
        {**package["decision"], "grant": context["grant"]},
    )
    with pytest.raises(ValueError, match="EXACT_AMENDMENT_REQUIRED"):
        owner.load_package_owner_acceptance(
            root, package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )


def test_consumed_quality_repair_grant_cannot_approve_format_successor(
    package: dict[str, Any],
) -> None:
    """TEST_ONLY latest consumed predecessor pins cannot approve new bytes."""
    root = package["root"]
    context = dict(package["context"])
    grant = json.loads((root / context["grant"]["path"]).read_text())
    review = grant["review_subject"]
    review["baseline_commit"] = "72cf9ca3a926508b499601f55d8fda857c452186"
    review["documents"][0].update(
        before_version="2.0.12",
        version="2.0.13",
        before_sha256="fe770aaf518bb413dd9ed99654f8cd974ac016dec775563cd14eff7741651b14",
    )
    context["grant"] = _write(root, context["grant"]["path"], grant)
    _write(root, CONTEXT_PATH, context)
    _write(
        root,
        package["policy"]["normative_decision_ref"],
        {**package["decision"], "grant": context["grant"]},
    )
    with pytest.raises(ValueError, match="EXACT_AMENDMENT_REQUIRED"):
        owner.load_package_owner_acceptance(
            root, package["change_set"].changed_paths, "C3_GOVERNED", now=NOW
        )

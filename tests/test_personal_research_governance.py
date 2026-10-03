"""Synthetic fixtures only: no production identity, appointment, or approval."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, cast

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
    GovernanceGateReport,
    build_governance_gate_report,
    load_approval_records,
    load_repository_validator_evidence,
)
from ai4binance.governance.personal_research import (
    AUTHORITY_PATHS,
    FROZEN_REPAIR_BASELINE,
    FROZEN_REPAIR_OUTPUTS,
    FROZEN_REPAIR_TREE,
    POLICY_PATH,
    SCHEMA_PATH,
    PersonalResearchConfirmation,
    UnappliedPatchSubject,
    load_personal_research_policy,
    parse_confirmation,
    verify_baseline_adoption,
    verify_frozen_initial_repair,
)
from ai4binance.schema_validation import (
    SchemaValidationError,
    validate_local_definition,
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

ROOT = Path(__file__).resolve().parents[1]
PATH = "docs/standards/research_fixture.md"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data) if path.suffix == ".yaml" else json.dumps(data),
        encoding="utf-8",
    )


def _policy(root: Path, *, active: bool = True) -> None:
    (root / SCHEMA_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / SCHEMA_PATH).write_bytes((ROOT / SCHEMA_PATH).read_bytes())
    policy = yaml.safe_load((ROOT / POLICY_PATH).read_text())
    policy.update(
        schema_version=1,
        activation_status="ACTIVE" if active else "INACTIVE",
        allowed_paths=[PATH],
        activation_record="runtime/artifacts/governance/test-only.json",
    )
    _write(root / POLICY_PATH, policy)
    for relative in AUTHORITY_PATHS:
        path = root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())
    receipt = root / "runtime/artifacts/governance/TEST_ONLY_RECEIPT.txt"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes(b"TEST_ONLY_NOT_HUMAN_APPROVAL")
    now = datetime.now(UTC)
    activation = {
        "schema_version": 1,
        "decision_kind": "PROSPECTIVE_OWNER_BASELINE_REPLACEMENT",
        "epoch_id": policy["epoch_id"],
        "owner_person_id": "TEST_ONLY_OWNER",
        "repository_root": str(root.resolve()),
        "policy_sha256": _hash((root / POLICY_PATH).read_bytes()),
        "prior_baseline_commit": "a" * 40,
        "reviewed_candidate_sha256": "b" * 64,
        "owner_confirmation_ref": "runtime/artifacts/governance/TEST_ONLY_RECEIPT.txt",
        "owner_confirmation_sha256": _hash(receipt.read_bytes()),
        "authority_bindings": {
            p: _hash((root / p).read_bytes()) for p in AUTHORITY_PATHS
        },
        "issued_at_utc": (now - timedelta(hours=1)).isoformat(),
        "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
        "revoked_at_utc": None,
        "human_person_count": 1,
        "independent_human_review": False,
        "previous_c3_approval": False,
        "historical_approval_gaps_closed": False,
        "external_obligations_waived": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    _write(root / policy["activation_record"], activation)


def _report(
    root: Path, records: tuple[ApprovalRecord, ...] = (), *, quality_pass: bool = True
) -> GovernanceGateReport:
    changes = _change_set(root, PATH)
    return build_governance_gate_report(
        repository_root=root,
        repository_validator=load_repository_validator_evidence(
            _write_validator_report(root)
        ),
        docs_hygiene=_docs_hygiene(True),
        artifact_hygiene=_artifact_hygiene(True),
        constitution_sync_tests=_constitution_sync_tests(True),
        deterministic_quality_gate=_quality_report(
            root, change_set=changes, passed=quality_pass
        ),
        change_set=changes,
        approval_records=records,
        require_change_set=True,
        enforce_approval=True,
    )


def _record(root: Path) -> ApprovalRecord:
    report = _report(root)
    assert report.subject_digest is not None
    policy = load_personal_research_policy(root)
    assert policy is not None
    quality = _quality_report(root, change_set=_change_set(root, PATH))
    now = datetime.now(UTC)
    return ApprovalRecord(
        WorkflowIdentity("TEST_ONLY_WORK", "TEST_ONLY_RUN", "TEST_ONLY_TRACE", now),
        "TEST_ONLY_APPROVAL",
        "TEST_ONLY_OWNER",
        "TEST_ONLY_SUBJECT",
        ApprovalStatus.APPROVED_FOR_RESEARCH,
        ("TEST_ONLY_EVIDENCE",),
        approver_role="PersonalResearchOwner",
        principal_id="TEST_ONLY_OWNER",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256=report.subject_digest.subject_id,
        scope_hash=_change_set(root, PATH).change_set_sha256,
        quality_gate_evidence_sha256=quality.gate_evidence_sha256,
        governance_gate_evidence_sha256=report.gate_evidence_sha256,
        evidence_hash=_approval_evidence_hash(quality, report),
        authority_family_sha256=report.subject_digest.authority_family_sha256,
        lifecycle_definition_sha256=_lifecycle_definition_sha256(),
        approved_at=now,
        expires_at=now + timedelta(minutes=10),
        research_confirmation=PersonalResearchConfirmation(
            policy.epoch_id,
            policy.owner_person_id,
            policy.policy_sha256,
            policy.activation_sha256,
        ),
    )


@pytest.fixture
def research_root(tmp_path: Path) -> Path:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    _stamp_authority_frontmatter(tmp_path)
    _policy(tmp_path)
    (tmp_path / PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / PATH).write_text("Test-only research documentation.\n")
    return tmp_path


def test_one_person_is_one_person_and_legacy_is_not_retroactively_approved(
    research_root: Path,
) -> None:
    record = _record(research_root)
    report = _report(research_root, (record,))
    verification = report.approval_verification
    assert verification is not None
    assert verification.status is ApprovalVerificationStatus.PASS
    assert (
        verification.required_approval_count
        == verification.observed_approval_count
        == 1
    )
    assert verification.to_payload()["independent_human_review"] is False
    assert verification.to_payload()["human_person_count"] == 1
    assert record.execution_allowed is False
    assert record.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: replace(r, scope_hash="0" * 64),
        lambda r: replace(r, subject_sha256="0" * 64),
        lambda r: replace(r, evidence_hash="0" * 64),
        lambda r: replace(r, quality_gate_evidence_sha256="0" * 64),
        lambda r: replace(r, governance_gate_evidence_sha256="0" * 64),
        lambda r: replace(r, authority_family_sha256="0" * 64),
        lambda r: replace(r, lifecycle_definition_sha256="0" * 64),
        lambda r: replace(r, research_confirmation=None),
        lambda r: replace(r, principal_id="OTHER_TEST_PERSON"),
        lambda r: replace(r, expires_at=None),
        lambda r: replace(r, approver_role="GovernanceOwner"),
        lambda r: replace(r, revoked_at=datetime.now(UTC) + timedelta(hours=1)),
    ],
)
def test_existing_binding_and_identity_vetoes_remain(
    research_root: Path, mutate: Callable[[ApprovalRecord], ApprovalRecord]
) -> None:
    record = mutate(_record(research_root))
    report = _report(research_root, (record,))
    assert report.approval_verification is not None
    assert (
        report.approval_verification.status
        is ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    )


def test_duplicate_aliases_never_make_two_people(research_root: Path) -> None:
    record = _record(research_root)
    alias = replace(
        record, approval_id="TEST_ONLY_SECOND", approver_id="TEST_ONLY_ALIAS"
    )
    report = _report(research_root, (record, alias))
    assert "APPROVAL_PRINCIPAL_IDENTITY_COLLISION" in report.blockers
    assert report.approval_verification is not None
    assert report.approval_verification.human_person_count == 1


def test_failed_technical_gate_stays_blocked(research_root: Path) -> None:
    report = _report(research_root, (_record(research_root),), quality_pass=False)
    assert "DETERMINISTIC_QUALITY_GATE_NOT_PASSING" in report.blockers


def test_inactive_policy_keeps_two_record_legacy_rule(research_root: Path) -> None:
    _policy(research_root, active=False)
    report = _report(research_root)
    assert report.approval_verification is not None
    assert report.approval_verification.required_approval_count == 2
    assert report.approval_verification.approval_profile == "LEGACY_C3"


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_sha256": "0" * 64},
        {"repository_root": "C:/unrelated"},
        {"epoch_id": "wrong"},
        {"revoked_at_utc": "2026-01-01T00:00:00Z"},
        {"expires_at_utc": "2000-01-01T00:00:00Z"},
        {"independent_human_review": True},
        {"human_person_count": 2},
        {"previous_c3_approval": True},
        {"execution_allowed": True},
        {"external_obligations_waived": True},
    ],
)
def test_activation_drift_or_unsafe_claims_fail_closed(
    research_root: Path, changes: dict[str, object]
) -> None:
    path = research_root / "runtime/artifacts/governance/test-only.json"
    payload = yaml.safe_load(path.read_text())
    payload.update(changes)
    _write(path, payload)
    with pytest.raises((ValueError, SchemaValidationError)):
        load_personal_research_policy(research_root)


def test_policy_cannot_activate_itself_or_escape_root(research_root: Path) -> None:
    path = research_root / POLICY_PATH
    payload = yaml.safe_load(path.read_text())
    payload["activation_record"] = (
        "runtime/artifacts/governance/../../../../outside.json"
    )
    _write(path, payload)
    with pytest.raises(ValueError, match="PATH_ESCAPE"):
        load_personal_research_policy(research_root)


def test_excluded_scope_cannot_use_personal_confirmation(research_root: Path) -> None:
    policy = load_personal_research_policy(research_root)
    assert policy is not None
    with pytest.raises(ValueError, match="SCOPE_INELIGIBLE"):
        policy.check_scope(("src/ai4binance/governance/gate.py",), "C3_GOVERNED")
    with pytest.raises(ValueError, match="SCOPE_INELIGIBLE"):
        policy.check_scope((PATH,), "C4_CONSEQUENTIAL")


def test_runtime_activation_drift_invalidates_same_subject_record(
    research_root: Path,
) -> None:
    record = _record(research_root)
    path = research_root / "runtime/artifacts/governance/test-only.json"
    path.write_bytes(path.read_bytes() + b"\n")
    assert (
        "PERSONAL_RESEARCH_CONFIRMATION_MISMATCH"
        in _report(research_root, (record,)).blockers
    )


def test_confirmation_parser_rejects_claimed_independence() -> None:
    c = PersonalResearchConfirmation(
        "TEST_ONLY_EPOCH", "TEST_ONLY_OWNER", "a" * 64, "b" * 64
    )
    assert parse_confirmation(asdict(c)) == c
    validate_local_definition(ROOT / SCHEMA_PATH, "confirmation", asdict(c))
    with pytest.raises(ValueError, match="ONE_HUMAN_REQUIRED"):
        parse_confirmation({**asdict(c), "independent_human_review": True})


@pytest.mark.parametrize("relative", AUTHORITY_PATHS)
def test_changed_authority_cannot_reuse_activation(
    research_root: Path, relative: str
) -> None:
    path = research_root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="AUTHORITY_DRIFT"):
        load_personal_research_policy(research_root)


def test_owner_receipt_hash_and_existence_are_mandatory(research_root: Path) -> None:
    path = research_root / "runtime/artifacts/governance/TEST_ONLY_RECEIPT.txt"
    path.write_bytes(b"TEST_ONLY_CHANGED_RECEIPT")
    with pytest.raises(ValueError, match="RECEIPT_DRIFT"):
        load_personal_research_policy(research_root)


def test_future_personal_confirmation_is_rejected(research_root: Path) -> None:
    record = replace(
        _record(research_root), approved_at=datetime.now(UTC) + timedelta(minutes=1)
    )
    assert (
        "PERSONAL_RESEARCH_FUTURE_CONFIRMATION"
        in _report(research_root, (record,)).blockers
    )


def test_serialized_confirmation_uses_existing_loader_and_rejects_stale_epoch(
    research_root: Path,
) -> None:
    record = _record(research_root)
    payload = asdict(record)
    payload.pop("identity")
    for key in ("approved_at", "expires_at", "revoked_at"):
        value = payload.pop(key)
        payload[f"{key}_utc"] = value.isoformat() if value else None
    path = research_root / "runtime/artifacts/governance/TEST_ONLY_REPLAY.json"
    _write(path, {"approval_records": [payload]})
    report = _report(research_root, load_approval_records(path))
    assert report.approval_verification is not None
    assert report.approval_verification.status is ApprovalVerificationStatus.PASS
    payload["research_confirmation"]["epoch_id"] = "TEST_ONLY_STALE_EPOCH"
    _write(path, {"approval_records": [payload]})
    report = _report(research_root, load_approval_records(path))
    assert "PERSONAL_RESEARCH_CONFIRMATION_MISMATCH" in report.blockers


def test_unapplied_subject_binds_bytes_and_never_authorizes_application(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    subject = UnappliedPatchSubject(
        str(tmp_path),
        "a" * 40,
        _hash(b"patch"),
        _hash(b"evidence"),
        _hash(b"rollback"),
        _hash(b"authority"),
        "TEST_ONLY_EPOCH",
        (now + timedelta(minutes=10)).isoformat(),
        "b" * 40,
    )
    kwargs: _PatchInputs = {
        "baseline_commit": "a" * 40,
        "now": now,
        "evidence": b"evidence",
        "rollback": b"rollback",
        "authority": b"authority",
        "repository_root": str(tmp_path),
        "expected_tree": "b" * 40,
    }
    subject.verify(b"patch", **kwargs)
    validate_local_definition(
        ROOT / SCHEMA_PATH,
        "unapplied_patch_subject",
        json.loads(json.dumps(asdict(subject))),
    )
    with pytest.raises(ValueError, match="PATCH_SUBJECT_DRIFT"):
        subject.verify(b"changed", **kwargs)
    altered = kwargs.copy()
    altered["evidence"] = b"changed"
    with pytest.raises(ValueError, match="EVIDENCE_DRIFT"):
        subject.verify(b"patch", **altered)
    altered = kwargs.copy()
    altered["now"] = now + timedelta(hours=1)
    with pytest.raises(ValueError, match="EXPIRED"):
        subject.verify(b"patch", **altered)
    assert subject.subject_sha256 != replace(subject, epoch_id="OTHER").subject_sha256
    with pytest.raises(ValueError, match="NOT_EXECUTION_AUTHORITY"):
        replace(subject, permitted_operations=("APPLY_LOCAL",))


def test_frozen_repair_is_exact_transition_subject_only() -> None:
    inventory_path = (
        ROOT
        / "runtime/artifacts/quality/minimal-two-fix-successor-20261002/inventory.json"
    )
    inventory = json.loads(inventory_path.read_bytes())
    patch = (ROOT / inventory["patch_path"]).read_bytes()
    verify_frozen_initial_repair(
        ROOT,
        patch,
        expected_root=ROOT.resolve().as_posix(),
        baseline_commit=FROZEN_REPAIR_BASELINE,
        expected_tree=FROZEN_REPAIR_TREE,
        outputs=FROZEN_REPAIR_OUTPUTS,
        change_class="C3_GOVERNED",
    )
    assert {
        e["path"]: e["output_sha256"] for e in inventory["source_inventory"]
    } == FROZEN_REPAIR_OUTPUTS
    with pytest.raises(ValueError, match="INITIAL_REPAIR_NOT_EXACT_SUBJECT"):
        verify_frozen_initial_repair(
            ROOT,
            patch + b"x",
            expected_root=ROOT.resolve().as_posix(),
            baseline_commit=FROZEN_REPAIR_BASELINE,
            expected_tree=FROZEN_REPAIR_TREE,
            outputs=FROZEN_REPAIR_OUTPUTS,
            change_class="C3_GOVERNED",
        )
    with pytest.raises(ValueError, match="INITIAL_REPAIR_NOT_EXACT_SUBJECT"):
        verify_frozen_initial_repair(
            ROOT,
            patch,
            expected_root=ROOT.resolve().as_posix(),
            baseline_commit=FROZEN_REPAIR_BASELINE,
            expected_tree=FROZEN_REPAIR_TREE,
            outputs=FROZEN_REPAIR_OUTPUTS,
            change_class="C2_BEHAVIORAL",
        )


def _build_baseline_adoption(
    research_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], datetime]:
    from ai4binance.governance import document_lock_review as review
    from tests.test_document_lock_review import save

    root = research_root
    now = datetime.now(UTC)
    patch = (
        b"diff --git a/docs/standards/research_fixture.md "
        b"b/docs/standards/research_fixture.md\n"
    )
    refs = {
        name: save(root, f"runtime/artifacts/governance/TEST_ONLY_{name}.json", data)
        for name, data in (
            ("patch", {"TEST_ONLY": True}),
            ("evidence", {"TEST_ONLY": True}),
            ("rollback", {"TEST_ONLY": True}),
            ("authority", {"TEST_ONLY": True}),
        )
    }
    patch_path = root / refs["patch"]["path"]
    patch_path.write_bytes(patch)
    refs["patch"]["sha256"] = _hash(patch)
    subject = UnappliedPatchSubject(
        root.as_posix(),
        "a" * 40,
        refs["patch"]["sha256"],
        refs["evidence"]["sha256"],
        refs["rollback"]["sha256"],
        refs["authority"]["sha256"],
        "TEST_ONLY_EPOCH",
        (now + timedelta(minutes=10)).isoformat(),
        "b" * 40,
    )
    scope = [{"path": PATH, "output_sha256": _hash(b"TEST_ONLY_OUTPUT")}]
    frozen_inventory = (
        ROOT
        / "runtime/artifacts/quality/minimal-two-fix-successor-20261002/inventory.json"
    )
    frozen = json.loads(frozen_inventory.read_bytes())
    repair_path = root / "runtime/artifacts/governance/TEST_ONLY_frozen_repair.patch"
    repair_path.write_bytes((ROOT / frozen["patch_path"]).read_bytes())
    initial_repair = {
        "patch": {
            "path": repair_path.relative_to(root).as_posix(),
            "sha256": _hash(repair_path.read_bytes()),
        },
        "inventory": save(
            root,
            "runtime/artifacts/governance/TEST_ONLY_frozen_inventory.json",
            {"source_inventory": frozen["source_inventory"]},
        ),
        "baseline_commit": FROZEN_REPAIR_BASELINE,
        "expected_tree": FROZEN_REPAIR_TREE,
        "change_class": "C3_GOVERNED",
    }
    record = {
        "contract_version": "ProspectiveBaselineAdoption/v1",
        "decision_id": "TEST_ONLY_ADOPTION",
        "decision": "ADOPT_EXACT_PROSPECTIVE_BASELINE",
        "status": "ISSUED",
        "record_origin": "TEST_ONLY",
        "owner_person_id": "TEST_ONLY_OWNER",
        "repository_root": root.as_posix(),
        "epoch_id": subject.epoch_id,
        "baseline_commit": subject.baseline_commit,
        "expected_tree": subject.expected_tree,
        "subject_sha256": subject.subject_sha256,
        "source": save(
            root,
            "runtime/artifacts/governance/TEST_ONLY_owner_source.json",
            {"TEST_ONLY": True},
        ),
        "review_subject": save(
            root, "runtime/artifacts/governance/TEST_ONLY_subject.json", asdict(subject)
        ),
        **refs,
        "scope": scope,
        "source_inventory": save(
            root,
            "runtime/artifacts/governance/TEST_ONLY_inventory.json",
            {"source_inventory": scope},
        ),
        "initial_repair": initial_repair,
        "authority_bindings": {
            p: _hash((root / p).read_bytes()) for p in AUTHORITY_PATHS
        },
        "issued_at_utc": (now - timedelta(minutes=1)).isoformat(),
        "not_before_utc": (now - timedelta(minutes=1)).isoformat(),
        "expires_at_utc": (now + timedelta(minutes=10)).isoformat(),
        "revoked_at_utc": None,
        "human_confirmation": True,
        "natural_person_count": 1,
        "independent_human_review": False,
        "independently_verified_owner": False,
        "previous_c3_approval": False,
        "historical_approval_gaps_closed": False,
        "external_obligations_waived": False,
        "execution_allowed": False,
    }

    def git_text(actual_root: Path, *args: str) -> str:
        return actual_root.as_posix() if args[-1] == "--show-toplevel" else "a" * 40

    monkeypatch.setattr(review, "_git_text", git_text)
    monkeypatch.setattr(
        "ai4binance.governance.personal_research.BASELINE_ADOPTION_ORIGIN", "TEST_ONLY"
    )
    return record, now


def test_owner_baseline_adoption_is_review_only_and_not_self_activating(
    research_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, now = _build_baseline_adoption(research_root, monkeypatch)
    root = research_root
    result = verify_baseline_adoption(root, record, now=now)
    assert result["status"] == "BASELINE_ADOPTION_BINDINGS_VALID"
    assert result["application_allowed"] is False
    assert result["activation_allowed"] is False
    for change in (
        {"repository_root": "C:/TEST_ONLY_WRONG"},
        {"baseline_commit": "c" * 40},
        {"expected_tree": "d" * 40},
        {"scope": [{"path": "scripts/quality.ps1", "output_sha256": "a" * 64}]},
        {"expires_at_utc": (now - timedelta(seconds=1)).isoformat()},
        {"record_origin": "OWNER_ISSUED"},
        {"revoked_at_utc": now.isoformat()},
        {"independent_human_review": True},
        {"patch": {**record["patch"], "sha256": "0" * 64}},
        {"initial_repair": {**record["initial_repair"], "expected_tree": "d" * 40}},
    ):
        with pytest.raises((ValueError, SchemaValidationError)):
            verify_baseline_adoption(root, {**record, **change}, now=now)


def test_v2_adoption_binds_candidate_payloads_before_installation(
    research_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_document_lock_review import save

    root = research_root
    record, now = _build_baseline_adoption(root, monkeypatch)
    manifest_path = "config/governance/governed_document_lock_manifest.json"
    patch_path = root / record["patch"]["path"]
    patch = patch_path.read_bytes() + (
        f"diff --git a/{manifest_path} b/{manifest_path}\n".encode()
    )
    patch_path.write_bytes(patch)
    record["patch"]["sha256"] = _hash(patch)
    subject = json.loads((root / record["review_subject"]["path"]).read_bytes())
    subject["patch_sha256"] = record["patch"]["sha256"]
    record["review_subject"] = save(
        root, "runtime/artifacts/governance/TEST_ONLY_subject.json", subject
    )
    subject["permitted_operations"] = tuple(subject["permitted_operations"])
    record["subject_sha256"] = UnappliedPatchSubject(**subject).subject_sha256
    projection = b'{"TEST_ONLY":"projection"}'
    outputs = {PATH: b"TEST_ONLY_OUTPUT", manifest_path: projection}
    scope = [
        {"path": path, "output_sha256": _hash(data)} for path, data in outputs.items()
    ]
    record["scope"] = scope
    record["source_inventory"] = save(
        root,
        "runtime/artifacts/governance/TEST_ONLY_inventory.json",
        {"source_inventory": scope},
    )
    payloads = []
    for index, (path, data) in enumerate(outputs.items()):
        candidate = root / f"runtime/artifacts/governance/TEST_ONLY_payload_{index}"
        candidate.write_bytes(data)
        payloads.append(
            {
                "path": path,
                "payload": {
                    "path": candidate.relative_to(root).as_posix(),
                    "sha256": _hash(data),
                },
            }
        )
    record["payload_inventory"] = save(
        root,
        "runtime/artifacts/governance/TEST_ONLY_payloads.json",
        {"payloads": payloads},
    )
    record["registration_projection"] = payloads[1]["payload"]
    record["authority_bindings"] = {PATH: _hash(outputs[PATH])}
    record["contract_version"] = "ProspectiveBaselineAdoption/v2"
    monkeypatch.setattr(
        "ai4binance.governance.personal_research.AUTHORITY_PATHS", (PATH,)
    )
    (root / PATH).write_bytes(b"TEST_ONLY_OLD_CANONICAL_BYTES")
    artifact_root = root / "TEST_ONLY_isolated_artifacts"
    shutil.copytree(root / "runtime", artifact_root / "runtime")
    candidate_schema = artifact_root / SCHEMA_PATH
    candidate_schema.parent.mkdir(parents=True)
    shutil.copyfile(root / SCHEMA_PATH, candidate_schema)
    result = verify_baseline_adoption(
        root, record, now=now, artifact_root=artifact_root
    )
    assert result["application_allowed"] is False
    candidate = artifact_root / cast("dict[str, str]", payloads[0]["payload"])["path"]
    candidate.write_bytes(b"TEST_ONLY_TAMPER")
    with pytest.raises(ValueError, match="ARTIFACT_DRIFT"):
        verify_baseline_adoption(root, record, now=now, artifact_root=artifact_root)


def test_v2_installation_receipt_keeps_reviewed_and_installed_trees_distinct(
    research_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.governance import personal_research as research
    from tests.test_document_lock_review import save

    root = research_root
    reviewed_tree, installed_tree = "b" * 40, "c" * 40
    completed_at = "2026-10-02T01:00:00Z"
    adoption: dict[str, object] = {
        "contract_version": "ProspectiveBaselineAdoption/v2",
        "subject_sha256": "d" * 64,
        "patch": {"path": "runtime/TEST_ONLY_patch", "sha256": "e" * 64},
        "expected_tree": reviewed_tree,
        "baseline_commit": "a" * 40,
    }
    adoption_ref = save(root, "runtime/TEST_ONLY_adoption.json", adoption)
    instruction = save(root, "runtime/TEST_ONLY_instruction.json", {"TEST_ONLY": True})
    operation: dict[str, object] = {
        "contract_version": "ProspectiveBaselineOperationReceipt/v2",
        "status": "COMPLETED",
        "record_origin": "OPERATIONAL_INSTALLATION",
        "repository_root": root.as_posix(),
        "subject_sha256": adoption["subject_sha256"],
        "patch_sha256": cast("dict[str, str]", adoption["patch"])["sha256"],
        "reviewed_tree": reviewed_tree,
        "expected_tree": installed_tree,
        "completed_at_utc": completed_at,
    }
    receipt: dict[str, object] = {
        "contract_version": "ProspectiveBaselineInstallation/v2",
        "status": "COMPLETED",
        "record_origin": "OPERATIONAL_INSTALLATION",
        "repository_root": root.as_posix(),
        "epoch_id": "TEST_ONLY_EPOCH",
        "adoption": adoption_ref,
        "subject_sha256": adoption["subject_sha256"],
        "patch_sha256": cast("dict[str, str]", adoption["patch"])["sha256"],
        "reviewed_tree": reviewed_tree,
        "expected_tree": installed_tree,
        "completed_at_utc": completed_at,
        "application_instruction": instruction,
        "operation_receipt": save(root, "runtime/TEST_ONLY_operation.json", operation),
    }
    activation = {
        "baseline_adoption": adoption_ref,
        "installation_receipt": save(
            root, "runtime/TEST_ONLY_installation.json", receipt
        ),
        "issued_at_utc": "2026-10-02T02:00:00Z",
        "epoch_id": receipt["epoch_id"],
        "reviewed_candidate_sha256": receipt["patch_sha256"],
        "prior_baseline_commit": adoption["baseline_commit"],
    }
    monkeypatch.setattr(research, "verify_baseline_adoption", lambda *a, **k: {})
    research._baseline_installation(root, activation)
    operation["reviewed_tree"] = "f" * 40
    receipt["operation_receipt"] = save(
        root, "runtime/TEST_ONLY_operation.json", operation
    )
    activation["installation_receipt"] = save(
        root, "runtime/TEST_ONLY_installation.json", receipt
    )
    with pytest.raises(ValueError, match="INSTALLATION_BINDING"):
        research._baseline_installation(root, activation)


def test_v2_activation_requires_separate_completed_installation(
    research_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_document_lock_review import save

    root = research_root
    adoption, now = _build_baseline_adoption(root, monkeypatch)
    policy_path = root / POLICY_PATH
    policy = yaml.safe_load(policy_path.read_text())
    policy.update(schema_version=2, epoch_id=adoption["epoch_id"])
    _write(policy_path, policy)
    adoption_ref = save(
        root, "runtime/artifacts/governance/TEST_ONLY_baseline_adoption.json", adoption
    )
    completed_at = (now - timedelta(seconds=30)).isoformat()
    instruction = save(
        root, "runtime/artifacts/governance/TEST_ONLY_B.json", {"TEST_ONLY": True}
    )
    operation = {
        "contract_version": "ProspectiveBaselineOperationReceipt/v1",
        "status": "COMPLETED",
        "record_origin": "OPERATIONAL_INSTALLATION",
        "repository_root": root.as_posix(),
        "subject_sha256": adoption["subject_sha256"],
        "patch_sha256": adoption["patch"]["sha256"],
        "expected_tree": adoption["expected_tree"],
        "completed_at_utc": completed_at,
    }
    receipt = {
        "contract_version": "ProspectiveBaselineInstallation/v1",
        "status": "COMPLETED",
        "record_origin": "OPERATIONAL_INSTALLATION",
        "repository_root": root.as_posix(),
        "epoch_id": adoption["epoch_id"],
        "adoption": adoption_ref,
        "subject_sha256": adoption["subject_sha256"],
        "patch_sha256": adoption["patch"]["sha256"],
        "expected_tree": adoption["expected_tree"],
        "completed_at_utc": completed_at,
        "application_instruction": instruction,
        "operation_receipt": save(
            root, "runtime/artifacts/governance/TEST_ONLY_operation.json", operation
        ),
    }
    receipt_ref = save(
        root, "runtime/artifacts/governance/TEST_ONLY_installation.json", receipt
    )
    activation_path = root / policy["activation_record"]
    activation = yaml.safe_load(activation_path.read_text())
    activation.update(
        schema_version=2,
        epoch_id=adoption["epoch_id"],
        policy_sha256=_hash(policy_path.read_bytes()),
        prior_baseline_commit=adoption["baseline_commit"],
        reviewed_candidate_sha256=adoption["patch"]["sha256"],
        issued_at_utc=(now - timedelta(seconds=20)).isoformat(),
        expires_at_utc=(now + timedelta(minutes=10)).isoformat(),
        baseline_adoption=adoption_ref,
        installation_receipt=receipt_ref,
    )
    _write(activation_path, activation)
    assert load_personal_research_policy(root, now=now) is not None
    monkeypatch.setattr(
        "ai4binance.governance.personal_research.BASELINE_ADOPTION_ORIGIN",
        "OWNER_ISSUED",
    )
    with pytest.raises(ValueError, match="BASELINE_ADOPTION_ORIGIN"):
        load_personal_research_policy(root, now=now)
    monkeypatch.setattr(
        "ai4binance.governance.personal_research.BASELINE_ADOPTION_ORIGIN", "TEST_ONLY"
    )
    activation.pop("baseline_adoption")
    _write(activation_path, activation)
    with pytest.raises((ValueError, SchemaValidationError)):
        load_personal_research_policy(root, now=now)
    policy["activation_status"] = "INACTIVE"
    _write(policy_path, policy)
    assert load_personal_research_policy(root, now=now) is None


class _PatchInputs(TypedDict):
    baseline_commit: str
    now: datetime
    evidence: bytes
    rollback: bytes
    authority: bytes
    repository_root: str
    expected_tree: str

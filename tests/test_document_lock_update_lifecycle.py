"""TEST_ONLY owner transitions anchored to real isolated Git installations."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Self

import pytest

from ai4binance.governance import document_lock_authority as authority
from ai4binance.governance import document_lock_review as review
from tests.test_document_lock_authority import (
    _complete_chain,
    consume,
    write_chain,
)
from tests.test_document_lock_authority import (
    chain as chain,
)
from tests.test_document_lock_completed_baseline import commit, git
from tests.test_document_lock_review import NOW, bind, save

ORIGINAL_GIT_TEXT = review._git_text
MANIFEST = "config/governance/governed_document_lock_manifest.json"


def raw(root: Path, path: str, data: bytes) -> dict[str, str]:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest()}


@pytest.fixture
def installed(
    chain: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], dict[str, bytes]]:
    root, bundle = chain
    raw(
        root,
        "src/ai4binance/governance/document_lock_review.py",
        Path(review.__file__).read_bytes(),
    )
    git(root, "init")
    (root / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    (root / ".gitignore").write_text("runtime/\n", encoding="utf-8")
    old = (root / "AGENTS.md").read_bytes()
    baseline_doc = old.replace(b"version: 2.0.0", b"version: 1.0.0")
    (root / "AGENTS.md").write_bytes(baseline_doc)
    baseline = copy.deepcopy(bundle["projection"])
    baseline["locked_documents"][0].update(
        version="1.0.0",
        sha256=review._digest(baseline_doc),
        expected_hash=review._digest(baseline_doc),
    )
    save(root, MANIFEST, baseline)
    baseline_commit = commit(root)
    (root / "AGENTS.md").write_bytes(old)
    save(root, MANIFEST, bundle["projection"])
    git(root, "add", "AGENTS.md", MANIFEST)
    reviewed_tree = git(root, "write-tree")
    prior = bundle["prior"]
    decision = json.loads((root / prior["decision"]["path"]).read_bytes())
    decision["contract_version"] = "DocumentLockReview/v2"
    prior["contract_version"] = "DocumentLockReviewContext/v2"
    subject = decision["review_subject"]
    subject.update(
        baseline_commit=baseline_commit,
        expected_tree=reviewed_tree,
        candidate_payloads=[
            {
                "path": "AGENTS.md",
                "source": raw(root, "runtime/TEST_ONLY_original-doc.raw", old),
            }
        ],
    )
    for key in ("evidence", "authority"):
        inventory = json.loads((root / subject[key]["path"]).read_bytes())
        inventory["baseline_commit"] = baseline_commit
        subject[key] = save(root, subject[key]["path"], inventory)
    prior["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, prior)
    for key in ("context", "adoption", "grant"):
        bundle[key]["subject_sha256"] = decision["subject_sha256"]
    bundle["context"]["review_context"] = save(
        root, "runtime/TEST_ONLY_review_context.json", prior
    )
    write_chain(root, bundle)
    _complete_chain(root, bundle)
    context = bundle["context"]
    context["contract_version"] = "DocumentLockAuthorityContext/v3"
    context["final_manifest"] = raw(
        root,
        "runtime/TEST_ONLY_original-final-manifest.json",
        (root / MANIFEST).read_bytes(),
    )
    git(root, "add", "--all")
    installed_tree = git(root, "write-tree")
    commit(root)
    receipt = json.loads((root / context["completion"]["path"]).read_bytes())
    operation = json.loads((root / receipt["application_receipt"]["path"]).read_bytes())
    receipt.update(
        contract_version="DocumentLockCompletion/v2",
        reviewed_tree=reviewed_tree,
        expected_tree=installed_tree,
        final_manifest=context["final_manifest"],
    )
    operation.update(
        contract_version="DocumentLockApplicationReceipt/v2",
        reviewed_tree=reviewed_tree,
        expected_tree=installed_tree,
        final_manifest=context["final_manifest"],
    )
    receipt["application_receipt"] = save(
        root, "runtime/TEST_ONLY_application_receipt.json", operation
    )
    context["completion"] = save(root, "runtime/TEST_ONLY_completion.json", receipt)
    save(root, authority.CONTEXT_PATH, context)
    monkeypatch.setattr(review, "_git_text", ORIGINAL_GIT_TEXT)
    monkeypatch.setattr(authority, "INSTALLATION_RECORD_ORIGIN", "TEST_ONLY")

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp((NOW + timedelta(hours=10)).timestamp(), tz)

    monkeypatch.setattr(authority, "datetime", Clock)
    assert consume(root)[2] is None
    frozen = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in (root / "runtime").rglob("*")
        if p.is_file()
    }
    return root, context, frozen


def update(root: Path, predecessor: dict[str, Any], *, number: int) -> dict[str, Any]:
    prefix = f"runtime/TEST_ONLY_update_{number}"
    before = json.loads((root / MANIFEST).read_bytes())
    predecessor = copy.deepcopy(predecessor)
    pred_ref = save(root, prefix + "/predecessor.json", predecessor)
    old = before["locked_documents"][0]
    version = f"{number + 2}.0.0"
    content = (
        (root / "AGENTS.md")
        .read_bytes()
        .replace(old["version"].encode(), version.encode())
    )
    projection = copy.deepcopy(before)
    projection["locked_documents"][0].update(
        version=version,
        sha256=review._digest(content),
        expected_hash=review._digest(content),
    )
    issued = NOW + timedelta(hours=number + 1)
    subject = {
        "repository_root": root.as_posix(),
        "epoch_id": f"TEST_ONLY_UPDATE_{number}",
        "baseline_commit": git(root, "rev-parse", "HEAD"),
        "predecessor": pred_ref,
        "predecessor_manifest": predecessor["final_manifest"],
        "registration_manifest": save(root, prefix + "/projection.json", projection),
        "documents": [
            {
                "path": "AGENTS.md",
                "document_id": "TEST_ONLY_DOC",
                "before_version": old["version"],
                "before_sha256": old["sha256"],
                "before_payload": raw(
                    root,
                    prefix + "/before-document.raw",
                    (root / "AGENTS.md").read_bytes(),
                ),
                "version": version,
                "sha256": review._digest(content),
                "payload": raw(root, prefix + "/document.raw", content),
            }
        ],
        "procedure": [
            {
                "path": p,
                "sha256": review._digest((root / p).read_bytes()),
                "source": raw(
                    root, prefix + f"/procedure-{i}.raw", (root / p).read_bytes()
                ),
            }
            for i, p in enumerate(authority.UPDATE_PROCEDURE_PATHS)
        ],
        **{
            k: save(root, prefix + f"/{k}.json", {"TEST_ONLY": k})
            for k in ("patch", "evidence", "rollback")
        },
    }
    grant = {
        "contract_version": "WrittenOwnerDocumentLockUpdate/v1",
        "status": "ISSUED",
        "record_origin": "TEST_ONLY",
        "decision_id": f"TEST_ONLY_GRANT_{number}",
        "decision": (
            "ADOPT_SUCCESSOR_PROCEDURE_AND_APPLY"
            if predecessor["contract_version"] == "DocumentLockAuthorityContext/v3"
            else "APPLY_DOCUMENT_UPDATE"
        ),
        "departure_from_legacy_c3": False,
        "previous_c3_approval": False,
        "historical_approval_gaps_closed": False,
        "owner_person_id": predecessor["owner_person_id"],
        "source": save(
            root, prefix + "/source.json", {"TEST_ONLY_NO_HUMAN_DECISION": True}
        ),
        "subject_sha256": review._digest(
            json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
        ),
        "review_subject": subject,
        "issued_at_utc": issued.isoformat(),
        "not_before_utc": issued.isoformat(),
        "expires_at_utc": (issued + timedelta(hours=1)).isoformat(),
        "revoked_at_utc": None,
        "human_confirmation": True,
        "natural_person_count": 1,
        "independent_human_review": False,
        "max_application_count": 1,
        "final_candidate_acceptance": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    grant["custody"] = {
        "custodian_person_id": grant["owner_person_id"],
        "attribution_confirmed": True,
        "ownership_basis": "SELF_DECLARED_PERSONAL_REPOSITORY_OWNER",
        "independent_identity_verified": False,
        "decision_channel": "TEST_ONLY_NO_HUMAN_DECISION",
        "checked_at_utc": issued.isoformat(),
        "source": grant["source"],
    }
    grant_ref = save(root, prefix + "/grant.json", grant)
    final = copy.deepcopy(projection)
    final["prospective_lock_grant"] = {
        "contract_version": authority.UPDATE_MANIFEST,
        "grant": grant_ref,
        "predecessor": pred_ref,
    }
    final_ref = save(root, prefix + "/final-manifest.json", final)
    revocations = {
        "contract_version": "DocumentLockReviewRevocations/v1",
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "issued_at_utc": issued.isoformat(),
        "not_before_utc": issued.isoformat(),
        "expires_at_utc": grant["expires_at_utc"],
        "revoked_decision_ids": [],
        "revoked_owner_ids": [],
        "revoked_subjects": [],
    }
    context = {
        "contract_version": authority.UPDATE_CONTEXT,
        "repository_root": root.as_posix(),
        "owner_person_id": grant["owner_person_id"],
        "subject_sha256": grant["subject_sha256"],
        "grant": grant_ref,
        "predecessor": pred_ref,
        "final_manifest": final_ref,
        "revocations": save(root, prefix + "/revocations.json", revocations),
    }
    completion = {
        k: context[k]
        for k in (
            "repository_root",
            "subject_sha256",
            "grant",
            "predecessor",
            "final_manifest",
        )
    }
    completion.update(
        contract_version="DocumentLockUpdateCompletion/v1",
        status="COMPLETED",
        record_origin="TEST_ONLY",
        completed_at_utc=(issued + timedelta(minutes=30)).isoformat(),
        application_count=1,
        protections_restored=True,
        final_candidate_acceptance=False,
        execution_allowed=False,
    )
    context["completion"] = save(root, prefix + "/completion.json", completion)
    (root / "AGENTS.md").write_bytes(content)
    (root / MANIFEST).write_bytes((root / final_ref["path"]).read_bytes())
    save(root, authority.CONTEXT_PATH, context)
    return context


def test_two_authorized_updates_preserve_real_accepted_history(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]],
) -> None:
    root, original, frozen = installed
    first = update(root, original, number=1)
    assert consume(root)[2] is None
    commit(root)
    assert consume(root)[2] is None
    second = update(root, first, number=2)
    entries, pairs, error = consume(root)
    assert error is None
    assert entries["AGENTS.md"].version == "4.0.0"
    assert ("AGENTS.md", review._digest((root / "AGENTS.md").read_bytes())) in pairs
    assert second["subject_sha256"] != first["subject_sha256"]
    for path, data in frozen.items():
        if path != authority.CONTEXT_PATH:
            assert (root / path).read_bytes() == data


@pytest.mark.parametrize(
    "target", ["document", "manifest", "procedure", "historical_source"]
)
def test_unapproved_changes_fail_closed(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]], target: str
) -> None:
    root, original, _ = installed
    update(root, original, number=1)
    paths = {
        "document": "AGENTS.md",
        "manifest": MANIFEST,
        "procedure": authority.UPDATE_PROCEDURE_PATHS[0],
        "historical_source": original["adoption"]["path"],
    }
    (root / paths[target]).write_bytes(b"TEST_ONLY unauthorized tampering")
    assert consume(root)[2] is not None


@pytest.mark.parametrize(
    "change",
    [
        "draft",
        "wrong_subject",
        "expired",
        "revoked",
        "owner",
        "missing_predecessor",
        "wrong_predecessor",
        "missing_completion",
        "bad_completion",
        "revocation_snapshot",
        "custody_identity",
        "custody_time",
        "unapproved_c3_departure",
    ],
)
def test_invalid_current_authority_is_rejected(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]], change: str
) -> None:
    root, original, _ = installed
    context = update(root, original, number=1)
    grant_path = root / context["grant"]["path"]
    grant = json.loads(grant_path.read_bytes())
    if change == "draft":
        grant["status"] = "DRAFT"
    elif change == "wrong_subject":
        grant["subject_sha256"] = "0" * 64
    elif change == "expired":
        grant["expires_at_utc"] = grant["issued_at_utc"]
    elif change == "revoked":
        grant["revoked_at_utc"] = grant["issued_at_utc"]
    elif change == "owner":
        grant["owner_person_id"] = "TEST_ONLY_OTHER_PERSON"
    elif change == "missing_predecessor":
        del context["predecessor"]
    elif change == "wrong_predecessor":
        context["predecessor"]["sha256"] = "0" * 64
    elif change == "missing_completion":
        (root / context["completion"]["path"]).unlink()
    elif change == "bad_completion":
        receipt = json.loads((root / context["completion"]["path"]).read_bytes())
        receipt["application_count"] = 2
        context["completion"] = save(root, context["completion"]["path"], receipt)
    elif change == "custody_identity":
        grant["custody"]["custodian_person_id"] = "TEST_ONLY_OTHER_PERSON"
        rebind_update(root, context, grant)
    elif change == "unapproved_c3_departure":
        grant["departure_from_legacy_c3"] = True
        rebind_update(root, context, grant)
    elif change == "custody_time":
        grant["custody"]["checked_at_utc"] = (NOW - timedelta(days=1)).isoformat()
        rebind_update(root, context, grant)
    else:
        snapshot = json.loads((root / context["revocations"]["path"]).read_bytes())
        snapshot["revoked_decision_ids"] = [grant["decision_id"]]
        context["revocations"] = save(root, context["revocations"]["path"], snapshot)
    if change in {"draft", "wrong_subject", "expired", "revoked", "owner"}:
        rebind_update(root, context, grant, calculate_subject=False)
    save(root, authority.CONTEXT_PATH, context)
    assert consume(root)[2] is not None


def rebind_update(
    root: Path,
    context: dict[str, Any],
    grant: dict[str, Any],
    *,
    calculate_subject: bool = True,
) -> None:
    """Rehash TEST_ONLY inputs so semantic rejection cannot rely on stale digests."""
    subject = grant["review_subject"]
    if calculate_subject:
        grant["subject_sha256"] = review._digest(
            json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
        )
    context["subject_sha256"] = grant["subject_sha256"]
    context["grant"] = save(root, context["grant"]["path"], grant)
    final = json.loads((root / subject["registration_manifest"]["path"]).read_bytes())
    final["prospective_lock_grant"] = {
        "contract_version": authority.UPDATE_MANIFEST,
        "grant": context["grant"],
        "predecessor": context["predecessor"],
    }
    context["final_manifest"] = save(root, context["final_manifest"]["path"], final)
    completion = json.loads((root / context["completion"]["path"]).read_bytes())
    for key in ("subject_sha256", "grant", "final_manifest"):
        completion[key] = context[key]
    context["completion"] = save(root, context["completion"]["path"], completion)
    (root / MANIFEST).write_bytes(
        (root / context["final_manifest"]["path"]).read_bytes()
    )
    save(root, authority.CONTEXT_PATH, context)


@pytest.mark.parametrize(
    "change",
    [
        "approval_history",
        "authority",
        "before_document",
        "metadata",
        "scope",
        "duplicate",
    ],
)
def test_rehashed_semantic_changes_are_rejected(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]], change: str
) -> None:
    root, original, _ = installed
    context = update(root, original, number=1)
    grant = json.loads((root / context["grant"]["path"]).read_bytes())
    subject = grant["review_subject"]
    projection = json.loads(
        (root / subject["registration_manifest"]["path"]).read_bytes()
    )
    if change == "approval_history":
        projection["approval_records"].append(
            {"TEST_ONLY": "fabricated historical approval"}
        )
    elif change == "authority":
        projection["locked_documents"][0]["authority_level"] = "ROOT"
    elif change == "before_document":
        subject["documents"][0]["before_sha256"] = "0" * 64
    elif change == "metadata":
        subject["documents"][0]["document_id"] = "TEST_ONLY_WRONG_DOCUMENT"
    elif change == "scope":
        subject["documents"][0]["path"] = "TEST_ONLY_WRONG.md"
    else:
        subject["documents"].append(copy.deepcopy(subject["documents"][0]))
    subject["registration_manifest"] = save(
        root, subject["registration_manifest"]["path"], projection
    )
    rebind_update(root, context, grant)
    assert consume(root)[2] is not None


def test_completed_update_is_history_after_application_window(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]],
) -> None:
    root, original, _ = installed
    context = update(root, original, number=1)
    payload = json.loads((root / MANIFEST).read_bytes())
    pairs, _ = authority._verify_update(
        root, payload, context, now=NOW + timedelta(days=5)
    )
    assert ("AGENTS.md", review._digest((root / "AGENTS.md").read_bytes())) in pairs


def test_first_successor_requires_explicit_normative_adoption(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]],
) -> None:
    root, original, _ = installed
    context = update(root, original, number=1)
    grant = json.loads((root / context["grant"]["path"]).read_bytes())
    grant["decision"] = "APPLY_DOCUMENT_UPDATE"
    rebind_update(root, context, grant)
    assert "DOCUMENT_UPDATE_ADOPTION_REQUIRED" in (consume(root)[2] or "")


def test_production_consumer_rejects_test_only_owner_origin(
    installed: tuple[Path, dict[str, Any], dict[str, bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, original, _ = installed
    update(root, original, number=1)
    monkeypatch.setattr(authority, "OWNER_RECORD_ORIGIN", "OWNER_ISSUED")
    assert "DOCUMENT_UPDATE_OWNER_OR_SUBJECT" in (consume(root)[2] or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL transaction contract")
@pytest.mark.parametrize("fail", [False, True], ids=["success", "rollback"])
@pytest.mark.parametrize("matrix_locked", [False, True])
def test_windows_bounded_transaction_restores_real_protections(
    tmp_path: Path, fail: bool, matrix_locked: bool
) -> None:
    """Exercise native ACL/attribute ordering on two isolated TEST_ONLY files."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell is not None
    files = [tmp_path / "TEST_ONLY_document.md", tmp_path / "TEST_ONLY_manifest.json"]
    for path in files:
        path.write_bytes(b"TEST_ONLY original bytes\n")
    script = r"""
$ErrorActionPreference='Stop'
$paths=($env:AI4B_TEST_ONLY_TRANSACTION_PATHS | ConvertFrom-Json)
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$snapshots=@()
try {
    foreach ($p in $paths) {
        $acl=Get-Acl -LiteralPath $p
        # Persist the inherited ACL before the transaction baseline, as in
        # the inspected canonical files; retain exact SDDL equality below.
        Set-Acl -LiteralPath $p -AclObject $acl
        $acl=Get-Acl -LiteralPath $p
        $rights=[Security.AccessControl.FileSystemRights]::Write
        $type=[Security.AccessControl.AccessControlType]::Deny
        $deny=[Security.AccessControl.FileSystemAccessRule]::new($sid,$rights,$type)
        if ($p -eq $paths[0] -or
            $env:AI4B_TEST_ONLY_MATRIX_LOCKED -eq '1') {
            [IO.File]::SetAttributes($p,[IO.FileAttributes]::ReadOnly)
            [void]$acl.AddAccessRule($deny)
            Set-Acl -LiteralPath $p -AclObject $acl
        }
        $originalAcl=Get-Acl -LiteralPath $p
        $successAcl=Get-Acl -LiteralPath $p
        [void]$successAcl.AddAccessRule($deny)
        $snapshots+=@{
            path=$p
            bytes=[IO.File]::ReadAllBytes($p)
            sddl=$originalAcl.Sddl
            successSddl=$successAcl.Sddl
            attrs=[int](Get-Item -LiteralPath $p -Force).Attributes
        }
    }
    $succeeded=$false
    try {
        foreach ($s in $snapshots) {
            $acl=Get-Acl -LiteralPath $s.path
            $rules=@($acl.Access | Where-Object {
                -not $_.IsInherited -and $_.AccessControlType -eq 'Deny'
            })
            foreach ($r in $rules) {[void]$acl.RemoveAccessRuleSpecific($r)}
            Set-Acl -LiteralPath $s.path -AclObject $acl
            [IO.File]::SetAttributes($s.path,[IO.FileAttributes]::Normal)
            $bytes=[Text.Encoding]::UTF8.GetBytes('TEST_ONLY approved replacement')
            [IO.File]::WriteAllBytes($s.path,$bytes)
        }
        if ($env:AI4B_TEST_ONLY_TRANSACTION_FAIL -eq '1') {
            throw 'TEST_ONLY_INJECTED_FAILURE'
        }
        $succeeded=$true
    }
    catch {if ($_.Exception.Message -ne 'TEST_ONLY_INJECTED_FAILURE') {throw}}
    finally {
        foreach ($s in $snapshots) {
            if (-not $succeeded) {[IO.File]::WriteAllBytes($s.path,$s.bytes)}
            # Restore attributes while write access remains available, then ACL.
            $attrs=$s.attrs
            $sddl=$s.sddl
            if ($succeeded) {$attrs=$attrs -bor 1; $sddl=$s.successSddl}
            [IO.File]::SetAttributes($s.path,[IO.FileAttributes]$attrs)
            $acl=Get-Acl -LiteralPath $s.path
            $acl.SetSecurityDescriptorSddlForm(
                $sddl,[Security.AccessControl.AccessControlSections]::Access
            )
            Set-Acl -LiteralPath $s.path -AclObject $acl
        }
    }
    foreach ($s in $snapshots) {
        $currentAttrs=[int](Get-Item -LiteralPath $s.path -Force).Attributes
        $attrs=$s.attrs
        $sddl=$s.sddl
        if ($succeeded) {$attrs=$attrs -bor 1; $sddl=$s.successSddl}
        $aclChanged=(Get-Acl -LiteralPath $s.path).Sddl -ne $sddl
        if ($aclChanged -or $currentAttrs -ne $attrs) {
            $actualSddl=(Get-Acl -LiteralPath $s.path).Sddl
            Write-Output ('TEST_ONLY_EXPECTED '+$sddl.Replace($sid.Value,'SELF'))
            Write-Output ('TEST_ONLY_ACTUAL '+$actualSddl.Replace($sid.Value,'SELF'))
            $detail="attrs=$currentAttrs/$attrs acl=$aclChanged"
            throw "TEST_ONLY_PROTECTION_DRIFT $detail"
        }
        $actual=[Convert]::ToBase64String([IO.File]::ReadAllBytes($s.path))
        $original=[Convert]::ToBase64String($s.bytes)
        if (-not $succeeded -and $actual -ne $original) {
            throw 'TEST_ONLY_ROLLBACK_BYTES_DRIFT'
        }
    }
    Write-Output 'TEST_ONLY_TRANSACTION_VERIFIED'
}
finally {
    foreach ($p in $paths) {
        $acl=Get-Acl -LiteralPath $p
        $rules=@($acl.Access | Where-Object {
            -not $_.IsInherited -and $_.AccessControlType -eq 'Deny'
        })
        foreach ($r in $rules) {[void]$acl.RemoveAccessRuleSpecific($r)}
        Set-Acl -LiteralPath $p -AclObject $acl
        [IO.File]::SetAttributes($p,[IO.FileAttributes]::Normal)
    }
}
"""
    result = subprocess.run(  # noqa: S603 - isolated TEST_ONLY Windows files
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        env={
            **os.environ,
            "AI4B_TEST_ONLY_TRANSACTION_PATHS": json.dumps([str(p) for p in files]),
            "AI4B_TEST_ONLY_TRANSACTION_FAIL": "1" if fail else "0",
            "AI4B_TEST_ONLY_MATRIX_LOCKED": "1" if matrix_locked else "0",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEST_ONLY_TRANSACTION_VERIFIED" in result.stdout
    expected = (
        b"TEST_ONLY original bytes\n" if fail else b"TEST_ONLY approved replacement"
    )
    assert all(p.read_bytes() == expected for p in files)

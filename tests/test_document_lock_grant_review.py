"""TEST_ONLY prospective grant integration; fixtures have no human authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ai4binance.governance import document_lock_grant_review as grant_review
from ai4binance.governance import document_lock_review as review
from ai4binance.governance import repository_validator as validator
from tests.test_document_lock_review import NOW, PERIOD, bind, build_review_bundle, save


@pytest.fixture
def grant_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root, decision, prior = build_review_bundle(tmp_path, monkeypatch)
    subject = decision["review_subject"]
    grant = {
        **PERIOD,
        "contract_version": "DocumentLockGrantReview/v1",
        "grant_id": "TEST_ONLY_GRANT",
        "owner_person_id": decision["owner_person_id"],
        "subject_sha256": decision["subject_sha256"],
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "review_decision": prior["decision"],
        "revoked_at_utc": None,
        "requested_operations": [
            "UNLOCK_EXACT_DOCUMENTS",
            "REGISTER_EXACT_DOCUMENT_HASHES",
            "RELOCK_EXACT_DOCUMENTS",
        ],
        "purpose": "PRE_APPLICATION_GRANT_REVIEW",
        "record_origin": "TEST_ONLY",
        "application_allowed": False,
        "adoption_allowed": False,
        "execution_allowed": False,
        **{
            key: save(root, f"runtime/TEST_ONLY_{key}.json", {"test_only": True})
            for key in ("source", "baseline_replacement", "authority_procedure")
        },
    }
    context = {
        "contract_version": grant_review.CONTEXT,
        "review_context": save(root, "runtime/TEST_ONLY_context.json", prior),
        "grant": save(root, "runtime/TEST_ONLY_grant.json", grant),
    }
    projection = json.loads(
        (root / subject["registration_manifest"]["path"]).read_bytes()
    )
    final = {
        **projection,
        grant_review.MANIFEST_FIELD: {
            "contract_version": "DocumentLockRegistrationReview/v1",
            "grant": context["grant"],
        },
    }
    context["proposed_manifest"] = save(root, "runtime/TEST_ONLY_final.json", final)
    return root, grant, context


def rebind(root: Path, grant: dict[str, Any], context: dict[str, Any]) -> None:
    context["grant"] = save(root, "runtime/TEST_ONLY_grant.json", grant)
    final = json.loads((root / context["proposed_manifest"]["path"]).read_bytes())
    final[grant_review.MANIFEST_FIELD]["grant"] = context["grant"]
    context["proposed_manifest"] = save(root, "runtime/TEST_ONLY_final.json", final)


def test_grant_manifest_chain_validates_without_adoption(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
) -> None:
    root, grant, context = grant_bundle
    ref = save(root, "runtime/TEST_ONLY_grant_context.json", context)
    result = review.review_files(root, root / ref["path"], now=NOW)
    assert result["grant_status"] == "GRANT_BINDINGS_VALID"
    for field in (
        "application_allowed",
        "adoption_allowed",
        "execution_allowed",
        "lock_authority_recognized",
        "authority_procedure_adopted",
    ):
        assert result[field] is False
    approvals, error = validator._document_lock_approvals([grant], root)
    assert not approvals
    assert error is not None
    manifest = root / validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes((root / context["proposed_manifest"]["path"]).read_bytes())
    entries, approvals, error = validator._document_lock_manifest(root)
    assert not entries
    assert not approvals
    assert error is not None
    assert "DOCUMENT_GRANT_NOT_ADOPTED" in error


def test_v2_grant_review_uses_preinstallation_candidate_bytes(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
) -> None:
    root, grant, context = grant_bundle
    prior = json.loads((root / context["review_context"]["path"]).read_bytes())
    decision = json.loads((root / prior["decision"]["path"]).read_bytes())
    candidate = (root / "AGENTS.md").read_bytes()
    candidate_ref = root / "runtime/TEST_ONLY_candidate.md"
    candidate_ref.write_bytes(candidate)
    (root / "AGENTS.md").write_bytes(b"TEST_ONLY_OLD_CANONICAL_BYTES")
    decision["contract_version"] = "DocumentLockReview/v2"
    subject = decision["review_subject"]
    subject["candidate_payloads"] = [
        {
            "path": "AGENTS.md",
            "source": {
                "path": "runtime/TEST_ONLY_candidate.md",
                "sha256": hashlib.sha256(candidate).hexdigest(),
            },
        }
    ]
    prior["contract_version"] = "DocumentLockReviewContext/v2"
    prior["review_subject"] = subject
    bind(root, decision, prior)
    context["contract_version"] = "DocumentLockGrantReviewContext/v2"
    context["review_context"] = save(root, "runtime/TEST_ONLY_context.json", prior)
    grant["subject_sha256"] = decision["subject_sha256"]
    grant["review_decision"] = prior["decision"]
    rebind(root, grant, context)
    result = grant_review.review_grant_files(root, context, now=NOW, artifact_root=root)
    assert result["grant_status"] == "GRANT_BINDINGS_VALID"
    assert result["application_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_root", "C:/TEST_ONLY_OTHER"),
        ("epoch_id", "TEST_ONLY_OTHER"),
        ("subject_sha256", "f" * 64),
        ("owner_person_id", "TEST_ONLY_OTHER"),
        ("expires_at_utc", "2026-10-02T00:00:00Z"),
        ("expires_at_utc", "2026-10-04T00:00:00Z"),
        ("not_before_utc", "2026-10-03T00:00:00Z"),
        ("issued_at_utc", "2026-10-02T00:00:00"),
        ("requested_operations", ["APPLY_LOCAL"]),
        ("revoked_at_utc", "2026-10-01T00:00:00Z"),
        ("contract_version", "DocumentLockGrantReview/v999"),
        ("application_allowed", True),
        ("grant_id", " "),
    ],
)
def test_wrong_grant_bindings_fail_closed(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    field: str,
    value: object,
) -> None:
    root, grant, context = grant_bundle
    grant[field] = value
    rebind(root, grant, context)
    with pytest.raises(ValueError, match=r"DOCUMENT_|instance validation"):
        grant_review.review_grant_files(root, context, now=NOW)


@pytest.mark.parametrize(
    "field",
    ["source", "baseline_replacement", "authority_procedure", "review_decision"],
)
def test_tampered_grant_evidence_fails(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    field: str,
) -> None:
    root, grant, context = grant_bundle
    (root / grant[field]["path"]).write_bytes(b"TEST_ONLY_TAMPER")
    with pytest.raises(ValueError, match="DRIFT"):
        grant_review.review_grant_files(root, context, now=NOW)


@pytest.mark.parametrize("target", ["grant", "review", "owner", "subject"])
def test_current_revocation_rejects_grant_chain(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    target: str,
) -> None:
    root, grant, context = grant_bundle
    prior = json.loads((root / context["review_context"]["path"]).read_bytes())
    revocations = json.loads((root / prior["revocations"]["path"]).read_bytes())
    values = {
        "grant": ("revoked_decision_ids", grant["grant_id"]),
        "review": ("revoked_decision_ids", "TEST_ONLY_DECISION"),
        "owner": ("revoked_owner_ids", grant["owner_person_id"]),
        "subject": ("revoked_subjects", grant["subject_sha256"]),
    }
    key, value = values[target]
    revocations[key] = [value]
    prior["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", revocations)
    context["review_context"] = save(root, "runtime/TEST_ONLY_context.json", prior)
    with pytest.raises(ValueError, match="REVOKED"):
        grant_review.review_grant_files(root, context, now=NOW)


@pytest.mark.parametrize("mutation", ["history", "scope", "projection", "grant_hash"])
def test_final_manifest_cannot_widen_scope(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    mutation: str,
) -> None:
    root, _grant, context = grant_bundle
    final = json.loads((root / context["proposed_manifest"]["path"]).read_bytes())
    if mutation == "history":
        final["approval_records"] = [{"TEST_ONLY": True}]
    elif mutation == "scope":
        final["locked_documents"].append({"path": "TEST_ONLY_OTHER"})
    elif mutation == "projection":
        final["locked_documents"][0]["expected_hash"] = "f" * 64
    else:
        final[grant_review.MANIFEST_FIELD]["grant"]["sha256"] = "f" * 64
    context["proposed_manifest"] = save(root, "runtime/TEST_ONLY_final.json", final)
    with pytest.raises(ValueError, match="MANIFEST_SCOPE_MISMATCH"):
        grant_review.review_grant_files(root, context, now=NOW)


@pytest.mark.parametrize(
    "field", ["source", "grant_id", "authority_procedure", "expires_at_utc"]
)
def test_missing_required_grant_field_fails(
    grant_bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    field: str,
) -> None:
    root, grant, context = grant_bundle
    grant.pop(field)
    rebind(root, grant, context)
    with pytest.raises(ValueError, match="instance validation"):
        grant_review.review_grant_files(root, context, now=NOW)

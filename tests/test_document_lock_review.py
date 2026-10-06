"""TEST_ONLY pre-application records; no authenticated owner decisions."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any, Self

import pytest

from ai4binance.governance import document_lock_review as review
from ai4binance.governance import document_metadata as metadata
from ai4binance.governance import repository_validator as validator

NOW = datetime(2026, 10, 2, tzinfo=UTC)
PERIOD = {
    "issued_at_utc": "2026-10-01T00:00:00Z",
    "not_before_utc": "2026-10-01T00:00:00Z",
    "expires_at_utc": "2026-10-03T00:00:00Z",
}


def test_document_review_and_validator_share_the_metadata_reader(
    tmp_path: Path,
) -> None:
    document = tmp_path / "document.md"
    document.write_text(
        "---\ndocument_id: `TEST-ONLY-001`\nversion: '1.0.0'\n"
        "supersedes:\n  - OLD\n# Comment\n---\n# Body\n",
        encoding="utf-8",
    )
    assert metadata.read_document_frontmatter is review.read_document_frontmatter
    assert metadata.read_document_frontmatter is validator._frontmatter
    assert review.read_document_frontmatter(document) == {
        "document_id": "TEST-ONLY-001",
        "version": "1.0.0",
        "supersedes": "",
    }


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"document_id: TEST_ONLY_WITHOUT_FRONTMATTER\n",
        b"---\ndocument_id: TEST_ONLY_WITHOUT_CLOSING_DELIMITER\n",
        b"---\ndocument_id: \xff\n---\n",
    ],
    ids=["empty", "missing-opening", "missing-closing", "invalid-utf8"],
)
def test_shared_metadata_reader_rejects_invalid_frontmatter(
    tmp_path: Path, payload: bytes
) -> None:
    document = tmp_path / "test-only-invalid-document.md"
    document.write_bytes(payload)
    assert metadata.read_document_frontmatter(document) is None


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_shared_metadata_reader_accepts_scalar_frontmatter_line_endings(
    tmp_path: Path, line_ending: str
) -> None:
    document = tmp_path / "test-only-scalar-document.md"
    text = line_ending.join(
        ["---", "document_id: 'TEST_ONLY_SCALAR'", "version: `1.0.0`", "---", ""]
    )
    document.write_bytes(text.encode("utf-8"))
    assert metadata.read_document_frontmatter(document) == {
        "document_id": "TEST_ONLY_SCALAR",
        "version": "1.0.0",
    }


def test_shared_metadata_reader_preserves_missing_file_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        metadata.read_document_frontmatter(tmp_path / "test-only-missing-document.md")


def save(root: Path, name: str, value: object) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(data)
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}


def bind(root: Path, decision: dict[str, Any], context: dict[str, Any]) -> None:
    decision["subject_sha256"] = hashlib.sha256(
        json.dumps(
            decision["review_subject"], sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    context["decision"] = save(root, "runtime/TEST_ONLY_decision.json", decision)


@pytest.fixture
def bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    return build_review_bundle(tmp_path, monkeypatch)


def build_review_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = tmp_path.resolve()
    doc = root / "AGENTS.md"
    doc.write_text(
        "---\ndocument_id: TEST_ONLY_DOC\nversion: 2.0.0\n---\n# Test document\n"
    )
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    entry = {
        "path": "AGENTS.md",
        "version": "2.0.0",
        "sha256": digest,
        "expected_hash": digest,
    }
    baseline = {
        "locked_documents": [
            {**entry, "version": "1.0.0", "sha256": "b" * 64, "expected_hash": "b" * 64}
        ],
        "approval_records": [],
    }
    manifest = {"locked_documents": [entry], "approval_records": []}

    def git_text(actual_root: Path, *args: str) -> str:
        assert actual_root == root
        if args[0] == "show":
            return json.dumps(baseline)
        return root.as_posix() if args[-1] == "--show-toplevel" else "a" * 40

    monkeypatch.setattr(review, "_git_text", git_text)
    refs = {
        key: save(
            root, f"runtime/TEST_ONLY_{key}.json", {"test_only": True, "artifact": key}
        )
        for key in ("patch", "evidence", "rollback", "authority")
    }
    subject = {
        **refs,
        **PERIOD,
        "repository_root": root.as_posix(),
        "epoch_id": "TEST_ONLY_EXPECTED_EPOCH",
        "baseline_commit": "a" * 40,
        "expected_tree": "c" * 40,
        "registration_manifest": save(
            root, "runtime/TEST_ONLY_manifest.json", manifest
        ),
        "documents": [
            {
                "path": "AGENTS.md",
                "document_id": "TEST_ONLY_DOC",
                "version": "2.0.0",
                "sha256": digest,
            }
        ],
        "phase": "PRE_APPLICATION_REVIEW",
        "permitted_operations": ["REVIEW_DOCUMENT_REGISTRATION"],
    }
    inventory = {
        **PERIOD,
        "contract_version": "DocumentLockReviewArtifacts/v1",
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "baseline_commit": subject["baseline_commit"],
        "patch_sha256": refs["patch"]["sha256"],
        "artifacts": [
            save(root, "runtime/TEST_ONLY_observation.json", {"test_only": True})
        ],
    }
    for key in ("evidence", "authority"):
        subject[key] = save(root, f"runtime/TEST_ONLY_{key}.json", inventory)
    decision = {
        "contract_version": review.CONTRACT,
        "decision_id": "TEST_ONLY_DECISION",
        "owner_person_id": "TEST_ONLY_NOT_A_HUMAN",
        "natural_person_count": 1,
        "independent_human_review": False,
        "status": "REVIEW_ONLY",
        "review_subject": subject,
        "subject_sha256": "d" * 64,
        "revoked_at_utc": None,
        "application_allowed": False,
        "adoption_allowed": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    revocations = {
        **PERIOD,
        "contract_version": "DocumentLockReviewRevocations/v1",
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "revoked_decision_ids": [],
        "revoked_owner_ids": [],
        "revoked_subjects": [],
    }
    context = {
        "contract_version": "DocumentLockReviewContext/v1",
        "owner_person_id": decision["owner_person_id"],
        "review_subject": copy.deepcopy(subject),
        "revocations": save(root, "runtime/TEST_ONLY_revocations.json", revocations),
    }
    bind(root, decision, context)
    return root, decision, context


def test_valid_review_never_grants_authority(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]],
) -> None:
    root, decision, context = bundle
    result = review.verify_document_lock_review(root, decision, context, now=NOW)
    assert result["status"] == "REVIEW_BINDINGS_VALID"
    for field in (
        "application_allowed",
        "adoption_allowed",
        "execution_allowed",
        "owner_identity_authenticated",
        "independent_human_review",
    ):
        assert result[field] is False
    assert not (root / "config/governance/personal_research_policy.yaml").exists()
    assert validator._document_lock_approval_evidence(decision, root) is not None
    approvals, error = validator._document_lock_approvals([decision], root)
    assert not approvals
    assert error is not None
    assert result["human_confirmation_required"] is True


def test_v2_review_uses_pinned_candidate_before_canonical_installation(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, decision, context = bundle
    candidate = (root / "AGENTS.md").read_bytes()
    candidate_path = root / "runtime/TEST_ONLY_candidate.md"
    candidate_path.write_bytes(candidate)
    (root / "AGENTS.md").write_bytes(b"TEST_ONLY_OLD_CANONICAL_BYTES")
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
    decision["contract_version"] = "DocumentLockReview/v2"
    context["contract_version"] = "DocumentLockReviewContext/v2"
    context["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, context)
    artifact_root = root / "TEST_ONLY_isolated_payload_root"
    shutil.copytree(root / "runtime", artifact_root / "runtime")
    result = review.verify_document_lock_review(
        root, decision, context, now=NOW, artifact_root=artifact_root
    )
    assert result["application_allowed"] is False
    assert (root / "AGENTS.md").read_bytes() == b"TEST_ONLY_OLD_CANONICAL_BYTES"

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(NOW.timestamp(), tz)

    monkeypatch.setattr(validator, "datetime", Clock)
    context_ref = save(artifact_root, "runtime/TEST_ONLY_v2_context.json", context)
    args = [
        "--repository-root",
        str(root),
        "--document-lock-review-context",
        str(artifact_root / context_ref["path"]),
        "--document-lock-review-artifact-root",
        str(artifact_root),
    ]
    assert validator.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "REVIEW_BINDINGS_VALID"
    (artifact_root / candidate_path.relative_to(root)).write_bytes(b"TEST_ONLY_TAMPER")
    with pytest.raises(ValueError, match="ARTIFACT_DRIFT"):
        review.verify_document_lock_review(
            root, decision, context, now=NOW, artifact_root=artifact_root
        )


@pytest.mark.parametrize(
    "field",
    [
        "repository_root",
        "epoch_id",
        "baseline_commit",
        "expected_tree",
        "documents",
        "rollback",
        "evidence",
        "patch",
        "authority",
    ],
)
def test_expected_subject_mismatch_is_rejected(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], field: str
) -> None:
    root, decision, context = bundle
    context["review_subject"][field] = copy.deepcopy(decision["review_subject"][field])
    value = context["review_subject"][field]
    if isinstance(value, str):
        context["review_subject"][field] = "f" * len(value)
    elif isinstance(value, list):
        value[0]["version"] = "0.0.0"
    else:
        value["sha256"] = "f" * 64
    with pytest.raises(ValueError, match=r"DOCUMENT_REVIEW|instance validation"):
        review.verify_document_lock_review(root, decision, context, now=NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expires_at_utc", "2000-01-01T00:00:00Z"),
        ("not_before_utc", "2099-01-01T00:00:00Z"),
        ("issued_at_utc", "2099-01-01T00:00:00Z"),
        ("expires_at_utc", "2026-10-02T00:00:00Z"),
        ("expires_at_utc", "2030-01-01T00:00:00"),
        ("expires_at_utc", "not a timestamp"),
        ("repository_root", "C:/TEST_ONLY_WRONG_ROOT"),
        ("baseline_commit", "f" * 40),
        ("permitted_operations", ["APPLY_LOCAL"]),
        ("phase", "ADOPTED"),
    ],
)
def test_invalid_self_consistent_subject_is_rejected(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], field: str, value: object
) -> None:
    root, decision, context = bundle
    decision["review_subject"][field] = value
    context["review_subject"] = copy.deepcopy(decision["review_subject"])
    bind(root, decision, context)
    with pytest.raises(
        ValueError, match=r"DOCUMENT_REVIEW|instance validation|Invalid isoformat"
    ):
        review.verify_document_lock_review(root, decision, context, now=NOW)


@pytest.mark.parametrize(
    "field", ["patch", "evidence", "rollback", "authority", "registration_manifest"]
)
def test_tampered_or_missing_bytes_are_rejected(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], field: str
) -> None:
    root, decision, context = bundle
    (root / decision["review_subject"][field]["path"]).write_bytes(b"TEST_ONLY_TAMPER")
    with pytest.raises(ValueError, match="ARTIFACT_DRIFT"):
        review.verify_document_lock_review(root, decision, context, now=NOW)


@pytest.mark.parametrize(
    "field",
    [
        "contract_version",
        "review_subject",
        "revoked_at_utc",
        "subject_sha256",
        "owner_person_id",
        "application_allowed",
    ],
)
def test_required_decision_fields_cannot_be_omitted(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], field: str
) -> None:
    root, decision, context = bundle
    decision.pop(field)
    with pytest.raises(ValueError, match="instance validation"):
        review.verify_document_lock_review(root, decision, context, now=NOW)


@pytest.mark.parametrize(
    "field",
    [
        "revoked_decision_ids",
        "revoked_owner_ids",
        "revoked_subjects",
        "epoch_id",
        "repository_root",
        "expires_at_utc",
    ],
)
def test_revocation_status_is_mandatory_and_current(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], field: str
) -> None:
    root, decision, context = bundle
    value = json.loads((root / context["revocations"]["path"]).read_text())
    replacements = {
        "revoked_decision_ids": [decision["decision_id"]],
        "revoked_owner_ids": [decision["owner_person_id"]],
        "revoked_subjects": [decision["subject_sha256"]],
        "epoch_id": "TEST_ONLY_WRONG_EPOCH",
        "repository_root": "C:/TEST_ONLY_WRONG_ROOT",
        "expires_at_utc": "2000-01-01T00:00:00Z",
    }
    value[field] = replacements[field]
    context["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", value)
    with pytest.raises(ValueError, match="DOCUMENT_REVIEW"):
        review.verify_document_lock_review(root, decision, context, now=NOW)


@pytest.mark.parametrize(
    "mutation",
    [
        "document_bytes",
        "inventory_missing",
        "document_identity",
        "manifest_history",
        "manifest_extra_scope",
        "revoked",
        "decision_tamper",
        "unknown_version",
        "path_escape",
    ],
)
def test_registration_and_authority_attacks_fail_closed(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], mutation: str
) -> None:
    root, decision, context = bundle
    subject = decision["review_subject"]
    if mutation == "document_bytes":
        (root / "AGENTS.md").write_text("TEST_ONLY_TAMPER")
    elif mutation == "inventory_missing":
        subject["documents"] = []
    elif mutation == "document_identity":
        subject["documents"][0]["document_id"] = "WRONG"
    elif mutation.startswith("manifest_"):
        manifest = json.loads(
            (root / subject["registration_manifest"]["path"]).read_text()
        )
        if mutation == "manifest_history":
            manifest["approval_records"] = [{"TEST_ONLY": True}]
        else:
            manifest["locked_documents"][0]["lock_state"] = "UNLOCKED"
        subject["registration_manifest"] = save(
            root, "runtime/TEST_ONLY_manifest.json", manifest
        )
    elif mutation == "revoked":
        decision["revoked_at_utc"] = "2026-10-01T00:00:00Z"
    elif mutation == "unknown_version":
        decision["contract_version"] = "DocumentLockReview/v999"
    elif mutation == "path_escape":
        subject["patch"]["path"] = "../outside.json"
    context["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, context)
    if mutation == "decision_tamper":
        (root / context["decision"]["path"]).write_text("{}")
    with pytest.raises((ValueError, OSError)):
        review.verify_document_lock_review(root, decision, context, now=NOW)


def test_existing_validator_cli_consumes_review_files(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, _decision, context = bundle

    # Freeze CLI clock through the existing datetime binding, not authority state.
    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(NOW.timestamp(), tz)

    monkeypatch.setattr(validator, "datetime", Clock)
    context_ref = save(root, "runtime/TEST_ONLY_context.json", context)
    args = [
        "--repository-root",
        str(root),
        "--document-lock-review-context",
        str(root / context_ref["path"]),
    ]
    assert validator.main(args) == 0
    assert json.loads(capsys.readouterr().out)["adoption_allowed"] is False
    (root / context["decision"]["path"]).write_text("{}")
    assert validator.main(args) == 2
    assert json.loads(capsys.readouterr().out)["execution_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "wrong_patch",
        "wrong_epoch",
        "nested_tamper",
        "missing_file",
        "duplicate_json",
        "missing_revocations",
        "wrong_owner",
    ],
)
def test_stale_nested_and_missing_inputs_are_rejected(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]], mutation: str
) -> None:
    root, decision, context = bundle
    subject = decision["review_subject"]
    value = json.loads((root / subject["evidence"]["path"]).read_text())
    if mutation == "expired":
        value["expires_at_utc"] = "2000-01-01T00:00:00Z"
    elif mutation == "wrong_patch":
        value["patch_sha256"] = "f" * 64
    elif mutation == "wrong_epoch":
        value["epoch_id"] = "TEST_ONLY_WRONG_EPOCH"
    elif mutation == "nested_tamper":
        (root / value["artifacts"][0]["path"]).write_text("tampered")
    elif mutation == "missing_file":
        value["artifacts"][0]["path"] = "runtime/TEST_ONLY_MISSING"
    elif mutation == "missing_revocations":
        context.pop("revocations")
    elif mutation == "wrong_owner":
        context["owner_person_id"] = "TEST_ONLY_OTHER"
    subject["evidence"] = save(root, "runtime/TEST_ONLY_evidence.json", value)
    context["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, context)
    if mutation == "duplicate_json":
        path = root / context["decision"]["path"]
        path.write_text('{"decision_id":"TEST_ONLY_A","decision_id":"TEST_ONLY_B"}')
        context["decision"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError, OSError)):
        review.verify_document_lock_review(root, decision, context, now=NOW)


def test_review_cli_rejects_mixed_repository_validation_mode(
    bundle: tuple[Path, dict[str, Any], dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, _decision, context = bundle
    ref = save(root, "runtime/TEST_ONLY_context.json", context)
    assert (
        validator.main(
            [
                "--repository-root",
                str(root),
                "--document-lock-review-context",
                str(root / ref["path"]),
                "--check-repository",
            ]
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["blocker"]
        == "DOCUMENT_REVIEW_MODE_CONFLICT"
    )

"""TEST_ONLY adoption/grant chains through the ordinary manifest consumer."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any, Self

import pytest

from ai4binance.governance import document_lock_authority as authority
from ai4binance.governance import document_lock_review as review
from ai4binance.governance import repository_validator as validator
from tests.test_document_lock_review import NOW, bind, build_review_bundle, save

ROOT = Path(__file__).resolve().parents[1]
PERIOD = {
    "issued_at_utc": "2026-10-02T00:00:00Z",
    "not_before_utc": "2026-10-02T00:00:00Z",
    "expires_at_utc": "2026-10-02T23:00:00Z",
}


def write_chain(root: Path, bundle: dict[str, Any]) -> None:
    context = bundle["context"]
    context["adoption"] = save(
        root, "runtime/TEST_ONLY_adoption.json", bundle["adoption"]
    )
    bundle["grant"]["adoption"] = context["adoption"]
    context["grant"] = save(root, "runtime/TEST_ONLY_grant.json", bundle["grant"])
    manifest = copy.deepcopy(bundle["projection"])
    manifest["prospective_lock_grant"] = {
        "contract_version": authority.MANIFEST_CONTRACT,
        "adoption": context["adoption"],
        "grant": context["grant"],
    }
    context["final_manifest"] = save(
        root, validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH, manifest
    )
    save(root, authority.CONTEXT_PATH, context)


@pytest.fixture
def chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any]]:
    root, decision, prior = build_review_bundle(tmp_path, monkeypatch)
    subject = decision["review_subject"]
    real = json.loads(
        (ROOT / validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).read_bytes()
    )
    entry = copy.deepcopy(
        next(e for e in real["locked_documents"] if e["path"] == "AGENTS.md")
    )
    entry.update(
        version="2.0.0",
        sha256=subject["documents"][0]["sha256"],
        expected_hash=subject["documents"][0]["sha256"],
    )
    projection = {
        "status": "ACTIVE",
        "written_owner_approval_required": True,
        "manifest_lock_policy": real["manifest_lock_policy"],
        "approval_records": [],
        "written_owner_approvals": [],
        "locked_documents": [entry],
    }
    baseline = copy.deepcopy(projection)
    baseline["locked_documents"][0].update(
        version="1.0.0", sha256="b" * 64, expected_hash="b" * 64
    )

    def git_text(actual_root: Path, *args: str) -> str:
        assert actual_root == root
        if args[0] == "show":
            return json.dumps(baseline)
        return root.as_posix() if args[-1] == "--show-toplevel" else "a" * 40

    monkeypatch.setattr(review, "_git_text", git_text)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(NOW.timestamp(), tz)

    monkeypatch.setattr(authority, "datetime", Clock)
    monkeypatch.setattr(authority, "OWNER_RECORD_ORIGIN", "TEST_ONLY")
    revocations = json.loads((root / prior["revocations"]["path"]).read_bytes())
    revocations.update(PERIOD)
    prior["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", revocations)
    subject["registration_manifest"] = save(
        root, "runtime/TEST_ONLY_manifest.json", projection
    )
    prior["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, prior)
    common = {
        **PERIOD,
        "owner_person_id": decision["owner_person_id"],
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "subject_sha256": decision["subject_sha256"],
        "status": "ISSUED",
        "record_origin": "TEST_ONLY",
        "revoked_at_utc": None,
        "human_confirmation": True,
        "natural_person_count": 1,
        "independent_human_review": False,
        "previous_c3_approval": False,
        "historical_approval_gaps_closed": False,
        "execution_allowed": False,
    }
    procedure = [
        save(root, p, {"TEST_ONLY_PROCEDURE": p}) for p in authority.PROCEDURE_PATHS
    ]
    adoption = {
        **common,
        "contract_version": "DocumentLockAdoption/v1",
        "decision_id": "TEST_ONLY_ADOPTION",
        "departure_from_legacy_c3": True,
        "decision": "ADOPT_PROSPECTIVE_WRITTEN_OWNER_LOCK_CONTRACT",
        "procedure": procedure,
        "source": save(
            root, "runtime/TEST_ONLY_adoption_source.json", {"TEST_ONLY": True}
        ),
    }
    grant = {
        **common,
        "contract_version": "WrittenOwnerDocumentLockGrant/v1",
        "decision_id": "TEST_ONLY_GRANT",
        "adoption": {},
        "source": save(
            root, "runtime/TEST_ONLY_grant_source.json", {"TEST_ONLY": True}
        ),
        "registration_manifest": subject["registration_manifest"],
        "documents": subject["documents"],
        "permitted_effects": ["BOUNDED_UNLOCK", "REGISTER_EXACT_BYTES", "RELOCK"],
        "separate_application_authorization_required": True,
    }
    context = {
        **PERIOD,
        "contract_version": "DocumentLockAuthorityContext/v1",
        "repository_root": root.as_posix(),
        "epoch_id": subject["epoch_id"],
        "owner_person_id": decision["owner_person_id"],
        "subject_sha256": decision["subject_sha256"],
        "review_context": save(root, "runtime/TEST_ONLY_review_context.json", prior),
        "custody": {
            "custodian_person_id": decision["owner_person_id"],
            "attribution_confirmed": True,
            "ownership_basis": "SELF_DECLARED_PERSONAL_REPOSITORY_OWNER",
            "independent_identity_verified": False,
            "decision_channel": "TEST_ONLY_NO_HUMAN_CHANNEL",
            "checked_at_utc": PERIOD["issued_at_utc"],
            "adoption_source": adoption["source"],
            "grant_source": grant["source"],
        },
    }
    bundle = {
        "context": context,
        "adoption": adoption,
        "grant": grant,
        "projection": projection,
        "prior": prior,
    }
    write_chain(root, bundle)
    return root, bundle


def consume(
    root: Path,
) -> tuple[dict[str, Any], frozenset[tuple[str, str]], str | None]:
    with authority.authority_input(root, root / authority.CONTEXT_PATH):
        return validator._document_lock_manifest(root)


def test_exact_grant_reaches_actual_manifest_consumer(
    chain: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, bundle = chain
    entries, pairs, error = consume(root)
    assert error is None
    assert set(entries) == {"AGENTS.md"}
    assert pairs == frozenset(
        {("AGENTS.md", bundle["grant"]["documents"][0]["sha256"])}
    )
    assert not (root / "config/governance/personal_research_policy.yaml").exists()
    # Production has no TEST_ONLY switch; fixture monkeypatching is explicit.
    monkeypatch.setattr(authority, "OWNER_RECORD_ORIGIN", "OWNER_ISSUED")
    entries, pairs, error = validator._document_lock_manifest(root)
    assert not entries
    assert not pairs
    assert error is not None
    assert "ORIGIN" in error


@pytest.mark.parametrize(
    ("record", "field", "value"),
    [
        ("grant", "repository_root", "C:/TEST_ONLY_WRONG"),
        ("adoption", "epoch_id", "TEST_ONLY_WRONG"),
        ("grant", "subject_sha256", "f" * 64),
        ("grant", "documents", []),
        ("grant", "permitted_effects", ["APPLY_LOCAL"]),
        ("adoption", "departure_from_legacy_c3", False),
        ("grant", "expires_at_utc", "2026-10-02T00:00:00Z"),
        ("adoption", "expires_at_utc", "2026-10-01T23:00:00Z"),
        ("grant", "issued_at_utc", "2026-10-02T00:00:00"),
        ("grant", "human_confirmation", False),
        ("adoption", "status", "DRAFT"),
        ("grant", "revoked_at_utc", "2026-10-01T00:00:00Z"),
        ("grant", "separate_application_authorization_required", False),
        ("grant", "contract_version", "DocumentLockGrantReview/v1"),
    ],
)
def test_invalid_records_deny_manifest(
    chain: tuple[Path, dict[str, Any]],
    record: str,
    field: str,
    value: object,
) -> None:
    root, bundle = chain
    bundle[record][field] = value
    write_chain(root, bundle)
    entries, pairs, error = consume(root)
    assert not entries
    assert not pairs
    assert error is not None


@pytest.mark.parametrize(
    "field", ["adoption", "grant", "review_context", "custody", "final_manifest"]
)
def test_missing_context_denies(chain: tuple[Path, dict[str, Any]], field: str) -> None:
    root, bundle = chain
    bundle["context"].pop(field)
    save(root, authority.CONTEXT_PATH, bundle["context"])
    assert consume(root)[2] is not None


@pytest.mark.parametrize("target", ["adoption", "grant", "owner", "subject"])
def test_revocation_invalidates_recognition(
    chain: tuple[Path, dict[str, Any]], target: str
) -> None:
    root, bundle = chain
    prior = bundle["prior"]
    rev = json.loads((root / prior["revocations"]["path"]).read_bytes())
    ids = {
        "adoption": ("revoked_decision_ids", "TEST_ONLY_ADOPTION"),
        "grant": ("revoked_decision_ids", "TEST_ONLY_GRANT"),
        "owner": ("revoked_owner_ids", bundle["grant"]["owner_person_id"]),
        "subject": ("revoked_subjects", bundle["grant"]["subject_sha256"]),
    }
    field, value = ids[target]
    rev[field] = [value]
    prior["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", rev)
    bundle["context"]["review_context"] = save(
        root, "runtime/TEST_ONLY_review_context.json", prior
    )
    write_chain(root, bundle)
    assert "REVOKED" in str(consume(root)[2])


@pytest.mark.parametrize(
    "target",
    ["source", "procedure", "document", "manifest", "context", "scope", "custody"],
)
def test_tamper_and_scope_expansion_deny(
    chain: tuple[Path, dict[str, Any]],
    target: str,
) -> None:
    root, bundle = chain
    paths = {
        "source": bundle["grant"]["source"]["path"],
        "procedure": authority.PROCEDURE_PATHS[0],
        "document": "AGENTS.md",
        "manifest": validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH,
    }
    if target in paths:
        (root / paths[target]).write_bytes(b"TEST_ONLY_TAMPER")
    elif target == "context":
        bundle["context"]["epoch_id"] = "TEST_ONLY_OTHER"
        save(root, authority.CONTEXT_PATH, bundle["context"])
    elif target == "scope":
        bundle["projection"]["approval_records"].append({"TEST_ONLY": True})
        write_chain(root, bundle)
    else:
        bundle["context"]["custody"]["attribution_confirmed"] = False
        write_chain(root, bundle)
    assert consume(root)[2] is not None


def test_legacy_consumer_still_rejects_prospective_records(
    chain: tuple[Path, dict[str, Any]],
) -> None:
    root, bundle = chain
    for record in ("grant", "adoption"):
        pairs, error = validator._document_lock_approvals([bundle[record]], root)
        assert not pairs
        assert error is not None


def test_no_context_or_wrong_context_root_denies(
    chain: tuple[Path, dict[str, Any]],
) -> None:
    root, _bundle = chain
    with authority.authority_input(root.parent, root / authority.CONTEXT_PATH):
        assert "CONTEXT_ROOT" in str(validator._document_lock_manifest(root)[2])
    with authority.authority_input(root, root / "TEST_ONLY_MISSING"):
        assert validator._document_lock_manifest(root)[2] is not None


def test_grant_cannot_outlive_adoption(chain: tuple[Path, dict[str, Any]]) -> None:
    root, bundle = chain
    bundle["adoption"]["expires_at_utc"] = "2026-10-02T12:00:00Z"
    write_chain(root, bundle)
    assert "PERIOD" in str(consume(root)[2])


@pytest.mark.parametrize(
    "target", ["old_snapshot", "expired_snapshot", "old_custody", "wrong_epoch"]
)
def test_revocation_snapshot_and_custody_must_be_current(
    chain: tuple[Path, dict[str, Any]],
    target: str,
) -> None:
    root, bundle = chain
    prior = bundle["prior"]
    snapshot = json.loads((root / prior["revocations"]["path"]).read_bytes())
    if target == "old_snapshot":
        snapshot["issued_at_utc"] = "2026-10-01T23:00:00Z"
    elif target == "expired_snapshot":
        snapshot["expires_at_utc"] = PERIOD["issued_at_utc"]
    elif target == "wrong_epoch":
        snapshot["epoch_id"] = "TEST_ONLY_OTHER"
    else:
        bundle["context"]["custody"]["checked_at_utc"] = "2026-10-01T00:00:00Z"
    prior["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", snapshot)
    bundle["context"]["review_context"] = save(
        root, "runtime/TEST_ONLY_review_context.json", prior
    )
    write_chain(root, bundle)
    assert consume(root)[2] is not None


def _complete_chain(root: Path, bundle: dict[str, Any]) -> None:
    """Build a TEST_ONLY completed registration outside the operational origin."""
    context = bundle["context"]
    context["contract_version"] = "DocumentLockAuthorityContext/v2"
    manifest = copy.deepcopy(bundle["projection"])
    manifest["prospective_lock_grant"] = {
        "contract_version": authority.COMPLETED_MANIFEST_CONTRACT,
        "adoption": context["adoption"],
        "grant": context["grant"],
    }
    context["final_manifest"] = save(
        root, validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH, manifest
    )
    completed_at = "2026-10-02T01:00:00Z"
    application = {
        "contract_version": "DocumentLockApplicationReceipt/v1",
        "status": "COMPLETED",
        "repository_root": root.as_posix(),
        "subject_sha256": context["subject_sha256"],
        "completed_at_utc": completed_at,
        "final_manifest": context["final_manifest"],
        "expected_tree": bundle["prior"]["review_subject"]["expected_tree"],
    }
    receipt = {
        "contract_version": "DocumentLockCompletion/v1",
        "status": "COMPLETED",
        "record_origin": "TEST_ONLY",
        "repository_root": root.as_posix(),
        "epoch_id": context["epoch_id"],
        "subject_sha256": context["subject_sha256"],
        "adoption": context["adoption"],
        "grant": context["grant"],
        "final_manifest": context["final_manifest"],
        "expected_tree": application["expected_tree"],
        "completed_at_utc": completed_at,
        "application_receipt": save(
            root, "runtime/TEST_ONLY_application_receipt.json", application
        ),
    }
    context["completion"] = save(root, "runtime/TEST_ONLY_completion.json", receipt)
    save(root, authority.CONTEXT_PATH, context)


def test_completed_registration_read_after_operation_expiry(
    chain: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, bundle = chain
    _complete_chain(root, bundle)

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 10, 4, tzinfo=tz)

    monkeypatch.setattr(authority, "datetime", LaterClock)
    monkeypatch.setattr(authority, "INSTALLATION_RECORD_ORIGIN", "TEST_ONLY")
    assert consume(root)[2] is None
    monkeypatch.setattr(
        authority, "INSTALLATION_RECORD_ORIGIN", "OPERATIONAL_INSTALLATION"
    )
    assert "ORIGIN" in str(consume(root)[2])
    # The original v1 operation grant remains expired for new operations.
    write_chain(root, bundle)
    assert consume(root)[2] is not None


def test_v3_completion_separates_reviewed_and_installed_trees(
    chain: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, bundle = chain
    prior = bundle["prior"]
    decision = json.loads((root / prior["decision"]["path"]).read_bytes())
    subject = decision["review_subject"]
    candidate = (root / "AGENTS.md").read_bytes()
    candidate_path = root / "runtime/TEST_ONLY_candidate_document.md"
    candidate_path.write_bytes(candidate)
    subject["candidate_payloads"] = [
        {
            "path": "AGENTS.md",
            "source": {
                "path": "runtime/TEST_ONLY_candidate_document.md",
                "sha256": hashlib.sha256(candidate).hexdigest(),
            },
        }
    ]
    decision["contract_version"] = "DocumentLockReview/v2"
    prior["contract_version"] = "DocumentLockReviewContext/v2"
    prior["review_subject"] = copy.deepcopy(subject)
    bind(root, decision, prior)
    bundle["adoption"]["subject_sha256"] = decision["subject_sha256"]
    bundle["grant"]["subject_sha256"] = decision["subject_sha256"]
    bundle["context"]["subject_sha256"] = decision["subject_sha256"]
    bundle["context"]["review_context"] = save(
        root, "runtime/TEST_ONLY_review_context.json", prior
    )
    write_chain(root, bundle)
    _complete_chain(root, bundle)
    context = bundle["context"]
    context["contract_version"] = "DocumentLockAuthorityContext/v3"
    receipt = json.loads((root / context["completion"]["path"]).read_bytes())
    operation = json.loads((root / receipt["application_receipt"]["path"]).read_bytes())
    reviewed_tree = bundle["prior"]["review_subject"]["expected_tree"]
    installed_tree = "d" * 40
    prior_git_text = review._git_text

    def completed_git_text(actual_root: Path, *args: str) -> str:
        if args[0] == "log":
            return f"{'f' * 40} {installed_tree}"
        return prior_git_text(actual_root, *args)

    def completed_git_bytes(actual_root: Path, *args: str) -> bytes:
        assert args[0] == "show"
        assert args[1].startswith("f" * 40 + ":")
        return (actual_root / args[1].split(":", 1)[1]).read_bytes()

    monkeypatch.setattr(review, "_git_text", completed_git_text)
    monkeypatch.setattr(review, "_git_bytes", completed_git_bytes)
    receipt.update(
        contract_version="DocumentLockCompletion/v2",
        reviewed_tree=reviewed_tree,
        expected_tree=installed_tree,
    )
    operation.update(
        contract_version="DocumentLockApplicationReceipt/v2",
        reviewed_tree=reviewed_tree,
        expected_tree=installed_tree,
    )
    receipt["application_receipt"] = save(
        root, "runtime/TEST_ONLY_application_receipt.json", operation
    )
    context["completion"] = save(root, "runtime/TEST_ONLY_completion.json", receipt)
    save(root, authority.CONTEXT_PATH, context)
    monkeypatch.setattr(authority, "INSTALLATION_RECORD_ORIGIN", "TEST_ONLY")

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 10, 4, tzinfo=tz)

    monkeypatch.setattr(authority, "datetime", LaterClock)
    assert consume(root)[2] is None
    receipt["reviewed_tree"] = "e" * 40
    context["completion"] = save(root, "runtime/TEST_ONLY_completion.json", receipt)
    save(root, authority.CONTEXT_PATH, context)
    assert "COMPLETION_BINDING" in str(consume(root)[2])


@pytest.mark.parametrize(
    "change", ["completion_time", "root", "application", "manifest", "document"]
)
def test_completed_registration_rejects_invalid_bindings(
    chain: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    root, bundle = chain
    _complete_chain(root, bundle)
    monkeypatch.setattr(authority, "INSTALLATION_RECORD_ORIGIN", "TEST_ONLY")

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 10, 4, tzinfo=tz)

    monkeypatch.setattr(authority, "datetime", LaterClock)
    assert consume(root)[2] is None
    context = bundle["context"]
    receipt_path = root / context["completion"]["path"]
    receipt = json.loads(receipt_path.read_bytes())
    if change == "completion_time":
        receipt["completed_at_utc"] = "2026-10-03T01:00:00Z"
    elif change == "root":
        receipt["repository_root"] = "C:/TEST_ONLY_WRONG"
    elif change == "application":
        receipt["application_receipt"] = save(
            root, "runtime/TEST_ONLY_bad_application.json", {"status": "FAILED"}
        )
    elif change == "manifest":
        (root / validator.GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).write_bytes(
            b"TEST_ONLY_TAMPER"
        )
    else:
        (root / "AGENTS.md").write_bytes(b"TEST_ONLY_TAMPER")
    if change in {"completion_time", "root", "application"}:
        context["completion"] = save(root, context["completion"]["path"], receipt)
        save(root, authority.CONTEXT_PATH, context)
    assert consume(root)[2] is not None


def test_completed_registration_rejects_prior_revocation(
    chain: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, bundle = chain
    prior = bundle["prior"]
    snapshot = json.loads((root / prior["revocations"]["path"]).read_bytes())
    snapshot["revoked_decision_ids"] = ["TEST_ONLY_GRANT"]
    prior["revocations"] = save(root, "runtime/TEST_ONLY_revocations.json", snapshot)
    bundle["context"]["review_context"] = save(
        root, "runtime/TEST_ONLY_review_context.json", prior
    )
    _complete_chain(root, bundle)
    monkeypatch.setattr(authority, "INSTALLATION_RECORD_ORIGIN", "TEST_ONLY")

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 10, 4, tzinfo=tz)

    monkeypatch.setattr(authority, "datetime", LaterClock)
    assert "REVOKED" in str(consume(root)[2])

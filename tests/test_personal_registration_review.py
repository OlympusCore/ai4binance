"""TEST_ONLY registration acceptance probes; no human decision or activation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai4binance.governance import repository_validator as validator
from ai4binance.governance.document_lock_review import verify_document_lock_review
from ai4binance.governance.personal_research import AUTHORITY_PATHS
from tests.test_document_lock_review import NOW, bind, build_review_bundle
from tests.test_repository_validator import _write_document_lock_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "config/governance/governed_document_lock_manifest.json"
PATHS = tuple(path for path in AUTHORITY_PATHS if path.endswith(".md"))


def _save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def registered_root(tmp_path: Path) -> Path:
    for relative in PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    _write_document_lock_manifest(tmp_path, PATHS)
    return tmp_path


@pytest.mark.parametrize("relative", PATHS)
def test_ten_exact_registrations_are_readable(
    registered_root: Path, relative: str
) -> None:
    assert validator.read_verified_governed_document(registered_root, relative)


@pytest.mark.parametrize(
    ("field", "value"), [("version", "0.0.0"), ("sha256", "a" * 64)]
)
def test_stale_registration_is_rejected(
    registered_root: Path, field: str, value: str
) -> None:
    path = registered_root / MANIFEST
    payload = json.loads(path.read_text())
    payload["locked_documents"][0][field] = value
    _save(path, payload)
    with pytest.raises(ValueError, match="governed context"):
        validator.read_verified_governed_document(registered_root, PATHS[0])


def test_tampered_document_is_rejected(registered_root: Path) -> None:
    path = registered_root / PATHS[0]
    path.write_bytes(path.read_bytes() + b"\nTEST_ONLY_TAMPER\n")
    with pytest.raises(ValueError, match="lacks matching approval"):
        validator.read_verified_governed_document(registered_root, PATHS[0])


def test_unregistered_scope_is_rejected(registered_root: Path) -> None:
    with pytest.raises(ValueError, match="source is unavailable"):
        validator.read_verified_governed_document(
            registered_root, "docs/governance/TEST_ONLY_UNAUTHORIZED.md"
        )


@pytest.mark.parametrize("field", ["approval_scope", "approved_sha256"])
def test_lock_evidence_scope_tampering_is_rejected(tmp_path: Path, field: str) -> None:
    record = _test_record(tmp_path)
    path = tmp_path / str(record["approval_evidence_path"])
    evidence = json.loads(path.read_text())
    evidence[field] = "TEST_ONLY_WRONG_SCOPE"
    _save(path, evidence)
    record["approval_evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert validator._document_lock_approval_evidence(record, tmp_path) is not None


def _test_record(root: Path) -> dict[str, object]:
    record: dict[str, object] = {
        "approval_id": "TEST_ONLY_ACCEPTANCE_PROBE",
        "approval_scope": "TEST_ONLY_DOCUMENT_REGISTRATION",
        "approval_status": "APPROVED",
        "approved_by": "TEST_ONLY_NOT_A_HUMAN",
        "approved_at_utc": "2026-10-02T00:00:00Z",
        "written_owner_approval": True,
        "approved_sha256": {"AGENTS.md": "a" * 64},
        "test_only": True,
        "human_approval_issued": False,
    }
    payload = {
        **record,
        "artifact_origin": "governed_document_lock_written_owner_approval",
        "verification_status": "VERIFIED",
    }
    ref = "runtime/artifacts/governance/TEST_ONLY_ACCEPTANCE_PROBE.json"
    path = root / ref
    _save(path, payload)
    record.update(
        approval_evidence_path=ref,
        approval_evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert validator._document_lock_approval_evidence(record, root) is None
    return record


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_root", "C:/TEST_ONLY_WRONG_ROOT"),
        ("epoch_id", "TEST_ONLY_WRONG_EPOCH"),
        ("expires_at_utc", "2000-01-01T00:00:00Z"),
    ],
)
def test_adoption_binding_must_reject_invalid_lock_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    """The original acceptance requirement now exercises its explicit contract."""
    root, decision, context = build_review_bundle(tmp_path, monkeypatch)
    assert (
        verify_document_lock_review(root, decision, context, now=NOW)["status"]
        == "REVIEW_BINDINGS_VALID"
    )
    decision["review_subject"][field] = value
    bind(root, decision, context)
    with pytest.raises(ValueError, match="DOCUMENT_REVIEW_SUBJECT_OR_OWNER_MISMATCH"):
        verify_document_lock_review(root, decision, context, now=NOW)


def test_historical_root_provenance_does_not_become_adoption_authority(
    tmp_path: Path,
) -> None:
    record = _test_record(tmp_path)
    path = tmp_path / str(record["approval_evidence_path"])
    evidence = json.loads(path.read_text())
    evidence["repository_root"] = "C:/TEST_ONLY_HISTORICAL_ORIGIN"
    _save(path, evidence)
    record["approval_evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert validator._document_lock_approval_evidence(record, tmp_path) is None
    with pytest.raises(ValueError, match="instance validation"):
        verify_document_lock_review(tmp_path, evidence, {}, now=NOW)

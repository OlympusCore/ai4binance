"""Versioned pre-application evidence checks; never adoption or lock authority."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess  # nosec B404
from datetime import datetime
from pathlib import Path
from typing import Any

from ai4binance.governance.personal_research import UnappliedPatchSubject
from ai4binance.schema_validation import validate_local_definition

SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "schemas/governance/document_lock_review.schema.json"
)
CONTRACT = "DocumentLockReview/v1"
PROSPECTIVE_FIELDS = frozenset(
    {
        "contract_version",
        "epoch_id",
        "expires_at_utc",
        "not_before_utc",
        "revoked_at_utc",
        "review_subject",
        "decision_binding",
    }
)


def legacy_boundary_error(value: dict[str, object]) -> str | None:
    """Historical records are not implicitly upgraded into prospective decisions."""
    if PROSPECTIVE_FIELDS.intersection(value):
        return "Prospective review requires its versioned consumer; not lock approval."
    return None


def _object(path: Path) -> dict[str, Any]:
    return _decode(path.read_bytes())


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("DOCUMENT_REVIEW_DUPLICATE_JSON_KEY")
    return result


def _decode(data: bytes | str) -> dict[str, Any]:
    value = json.loads(data, object_pairs_hook=_unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("DOCUMENT_REVIEW_OBJECT_REQUIRED")
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("DOCUMENT_REVIEW_TIMEZONE_REQUIRED")
    return result


def _period(value: dict[str, Any], now: datetime) -> None:
    issued, start, end = (
        _time(value[k]) for k in ("issued_at_utc", "not_before_utc", "expires_at_utc")
    )
    if now.tzinfo is None or not issued <= start <= now < end:
        raise ValueError("DOCUMENT_REVIEW_PERIOD_INVALID_OR_STALE")


def _path(root: Path, relative: str) -> Path:
    parts = Path(relative)
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or parts.is_absolute()
        or ".." in parts.parts
    ):
        raise ValueError("DOCUMENT_REVIEW_PATH_INVALID")
    target = (root / parts).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("DOCUMENT_REVIEW_PATH_ESCAPE")
    return target


def _bound_bytes(root: Path, reference: dict[str, Any]) -> bytes:
    data = _path(root, reference["path"]).read_bytes()
    if _digest(data) != reference["sha256"]:
        raise ValueError("DOCUMENT_REVIEW_ARTIFACT_DRIFT")
    return data


def _git_bytes(root: Path, *arguments: str) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise ValueError("DOCUMENT_REVIEW_GIT_UNAVAILABLE")
    return subprocess.run(  # noqa: S603  # nosec B603
        [git, "-C", str(root), *arguments],
        capture_output=True,
        check=True,
        timeout=15,
    ).stdout


def _git_text(root: Path, *arguments: str) -> str:
    return _git_bytes(root, *arguments).decode("utf-8").strip()


def _baseline(root: Path, expected: str) -> None:
    for option, value in (("--show-toplevel", root.as_posix()), ("HEAD", expected)):
        result = _git_text(root, "rev-parse", option)
        if result != value:
            raise ValueError("DOCUMENT_REVIEW_BASELINE_OR_ROOT_DRIFT")


def _completed_baseline(
    root: Path, subject: dict[str, Any], installed_tree: str
) -> None:
    """Bind historical review to an actual accepted ancestor and installed bytes."""
    if _git_text(root, "rev-parse", "--show-toplevel") != root.as_posix():
        raise ValueError("DOCUMENT_REVIEW_BASELINE_OR_ROOT_DRIFT")
    history = _git_text(
        root,
        "log",
        "--format=%H %T",
        "--ancestry-path",
        f"{subject['baseline_commit']}..HEAD",
    )
    accepted = [
        row.split()[0]
        for row in history.splitlines()
        if len(row.split()) == 2 and row.split()[1] == installed_tree
    ]
    if len(accepted) != 1:
        raise ValueError("DOCUMENT_REVIEW_COMPLETED_TREE_NOT_ACCEPTED")
    commit = accepted[0]
    for document in subject["documents"]:
        relative = document["path"]
        committed = _git_bytes(root, "show", f"{commit}:{relative}")
        if (
            _digest(committed) != document["sha256"]
            or _path(root, relative).read_bytes() != committed
        ):
            raise ValueError("DOCUMENT_REVIEW_COMPLETED_DOCUMENT_DRIFT")
    manifest = "config/governance/governed_document_lock_manifest.json"
    if (
        _git_bytes(root, "show", f"{commit}:{manifest}")
        != _path(root, manifest).read_bytes()
    ):
        raise ValueError("DOCUMENT_REVIEW_COMPLETED_MANIFEST_DRIFT")


def _documents(
    root: Path, subject: dict[str, Any], *, artifacts_root: Path | None = None
) -> None:
    from ai4binance.governance.repository_validator import _frontmatter

    source_root = artifacts_root or root
    manifest = _decode(_bound_bytes(source_root, subject["registration_manifest"]))
    entries = manifest["locked_documents"]
    _registration_delta(root, subject, manifest)
    seen: set[str] = set()
    candidates = {
        item["path"]: item["source"] for item in subject.get("candidate_payloads", [])
    }
    if artifacts_root is not None and (
        len(candidates) != len(subject["documents"])
        or set(candidates) != {item["path"] for item in subject["documents"]}
    ):
        raise ValueError("DOCUMENT_REVIEW_CANDIDATE_SCOPE")
    for doc in subject["documents"]:
        relative = doc["path"]
        if relative in seen:
            raise ValueError("DOCUMENT_REVIEW_DUPLICATE_DOCUMENT")
        seen.add(relative)
        path = (
            _path(source_root, candidates[relative]["path"])
            if artifacts_root is not None
            else _path(root, relative)
        )
        if artifacts_root is not None:
            _bound_bytes(source_root, candidates[relative])
        metadata = _frontmatter(path) or {}
        matches = [e for e in entries if e["path"] == relative]
        if len(matches) != 1:
            raise ValueError("DOCUMENT_REVIEW_REGISTRATION_MISSING_OR_DUPLICATE")
        registered = matches[0]
        observed = (
            metadata.get("document_id"),
            metadata.get("version"),
            _digest(path.read_bytes()),
            registered.get("version"),
            registered.get("sha256"),
            registered.get("expected_hash"),
        )
        expected = (
            doc["document_id"],
            doc["version"],
            doc["sha256"],
            doc["version"],
            doc["sha256"],
            doc["sha256"],
        )
        if observed != expected:
            raise ValueError("DOCUMENT_REVIEW_REGISTRATION_DRIFT")


def _registration_delta(
    root: Path, subject: dict[str, Any], manifest: dict[str, Any]
) -> None:
    baseline = json.loads(
        _git_text(
            root,
            "show",
            subject["baseline_commit"]
            + ":config/governance/governed_document_lock_manifest.json",
        )
    )
    prior = {e["path"]: e for e in baseline["locked_documents"]}
    changed: set[str] = set()
    seen: set[str] = set()
    for entry in manifest["locked_documents"]:
        path = entry["path"]
        if path in seen or path not in prior:
            raise ValueError("DOCUMENT_REVIEW_MANIFEST_SCOPE_INVALID")
        seen.add(path)
        if entry != prior[path]:
            delta = {
                k
                for k in entry.keys() | prior[path].keys()
                if entry.get(k) != prior[path].get(k)
            }
            if not delta <= {"version", "expected_hash", "sha256"}:
                raise ValueError("DOCUMENT_REVIEW_MANIFEST_AUTHORITY_CHANGE")
            changed.add(path)
    if seen != set(prior) or changed != {d["path"] for d in subject["documents"]}:
        raise ValueError("DOCUMENT_REVIEW_INVENTORY_INCOMPLETE")
    if {k: v for k, v in manifest.items() if k != "locked_documents"} != {
        k: v for k, v in baseline.items() if k != "locked_documents"
    }:
        raise ValueError("DOCUMENT_REVIEW_HISTORICAL_RECORDS_CHANGED")


def _revocations(
    root: Path, context: dict[str, Any], decision: dict[str, Any], now: datetime
) -> None:
    value = _decode(_bound_bytes(root, context["revocations"]))
    validate_local_definition(SCHEMA, "revocations", value)
    _period(value, now)
    subject = decision["review_subject"]
    if (
        not all(decision[key].strip() for key in ("decision_id", "owner_person_id"))
        or not subject["epoch_id"].strip()
    ):
        raise ValueError("DOCUMENT_REVIEW_IDENTITY_REQUIRED")
    if (value["repository_root"], value["epoch_id"]) != (
        subject["repository_root"],
        subject["epoch_id"],
    ):
        raise ValueError("DOCUMENT_REVIEW_REVOCATION_SCOPE_MISMATCH")
    if (
        decision["revoked_at_utc"] is not None
        or decision["decision_id"] in value["revoked_decision_ids"]
        or decision["owner_person_id"] in value["revoked_owner_ids"]
        or decision["subject_sha256"] in value["revoked_subjects"]
    ):
        raise ValueError("DOCUMENT_REVIEW_REVOKED")


def verify_document_lock_review(
    root: Path,
    decision: dict[str, Any],
    context: dict[str, Any],
    *,
    now: datetime,
    artifact_root: Path | None = None,
    installed_tree: str | None = None,
) -> dict[str, object]:
    """Check pinned evidence without authenticating the caller's identity or custody."""
    validate_local_definition(SCHEMA, "decision", decision)
    validate_local_definition(SCHEMA, "context", context)
    root = root.resolve(strict=True)
    version = decision["contract_version"]
    if version == "DocumentLockReview/v1" and artifact_root is not None:
        raise ValueError("DOCUMENT_REVIEW_V1_ARTIFACT_ROOT")
    source_root = (
        artifact_root.resolve(strict=True) if artifact_root is not None else root
    )
    if (version == "DocumentLockReview/v2") != (
        context["contract_version"] == "DocumentLockReviewContext/v2"
    ):
        raise ValueError("DOCUMENT_REVIEW_CONTEXT_VERSION")
    if decision != _decode(_bound_bytes(source_root, context["decision"])):
        raise ValueError("DOCUMENT_REVIEW_DECISION_DRIFT")
    subject = decision["review_subject"]
    if (
        subject != context["review_subject"]
        or decision["owner_person_id"] != context["owner_person_id"]
    ):
        raise ValueError("DOCUMENT_REVIEW_SUBJECT_OR_OWNER_MISMATCH")
    if subject["repository_root"] != root.as_posix():
        raise ValueError("DOCUMENT_REVIEW_ROOT_MISMATCH")
    encoded = json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
    if _digest(encoded) != decision["subject_sha256"]:
        raise ValueError("DOCUMENT_REVIEW_SUBJECT_HASH_MISMATCH")
    _period(subject, now)
    if installed_tree is None:
        _baseline(root, subject["baseline_commit"])
    else:
        _completed_baseline(root, subject, installed_tree)
    patch_subject = UnappliedPatchSubject(
        repository_root=subject["repository_root"],
        baseline_commit=subject["baseline_commit"],
        patch_sha256=subject["patch"]["sha256"],
        evidence_sha256=subject["evidence"]["sha256"],
        rollback_sha256=subject["rollback"]["sha256"],
        authority_sha256=subject["authority"]["sha256"],
        epoch_id=subject["epoch_id"],
        expires_at_utc=subject["expires_at_utc"],
        expected_tree=subject["expected_tree"],
    )
    patch_subject.verify(
        _bound_bytes(source_root, subject["patch"]),
        baseline_commit=subject["baseline_commit"],
        now=now,
        evidence=_bound_bytes(source_root, subject["evidence"]),
        rollback=_bound_bytes(source_root, subject["rollback"]),
        authority=_bound_bytes(source_root, subject["authority"]),
        repository_root=root.as_posix(),
        expected_tree=subject["expected_tree"],
    )
    candidate_root = source_root if version == "DocumentLockReview/v2" else None
    _documents(root, subject, artifacts_root=candidate_root)
    _artifact_inventory(source_root, subject, "evidence", now)
    _artifact_inventory(source_root, subject, "authority", now)
    _revocations(source_root, context, decision, now)
    return {
        "status": "REVIEW_BINDINGS_VALID",
        "contract_version": version,
        "subject_sha256": decision["subject_sha256"],
        "application_allowed": False,
        "adoption_allowed": False,
        "owner_identity_authenticated": False,
        "independent_human_review": False,
        "human_confirmation_required": True,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _artifact_inventory(
    root: Path, subject: dict[str, Any], key: str, now: datetime
) -> None:
    value = _decode(_bound_bytes(root, subject[key]))
    validate_local_definition(SCHEMA, "artifact_inventory", value)
    _period(value, now)
    for field in ("repository_root", "epoch_id", "baseline_commit"):
        if value[field] != subject[field]:
            raise ValueError("DOCUMENT_REVIEW_EVIDENCE_SUBJECT_MISMATCH")
    if value["patch_sha256"] != subject["patch"]["sha256"]:
        raise ValueError("DOCUMENT_REVIEW_EVIDENCE_PATCH_MISMATCH")
    seen: set[str] = set()
    for entry in value["artifacts"]:
        if entry["path"] in seen:
            raise ValueError("DOCUMENT_REVIEW_DUPLICATE_EVIDENCE")
        seen.add(entry["path"])
        _bound_bytes(root, entry)


def review_files(
    root: Path,
    context_path: Path,
    *,
    now: datetime,
    artifact_root: Path | None = None,
) -> dict[str, object]:
    """Read a separately supplied review context; never read activation policy."""
    source_root = (
        artifact_root.resolve(strict=True) if artifact_root else root.resolve()
    )
    if not context_path.resolve(strict=True).is_relative_to(source_root):
        raise ValueError("DOCUMENT_REVIEW_CONTEXT_PATH_ESCAPE")
    context = _object(context_path)
    if context.get("contract_version") in {
        "DocumentLockGrantReviewContext/v1",
        "DocumentLockGrantReviewContext/v2",
    }:
        from ai4binance.governance.document_lock_grant_review import review_grant_files

        return review_grant_files(root, context, now=now, artifact_root=artifact_root)
    validate_local_definition(SCHEMA, "context", context)
    decision = _decode(_bound_bytes(source_root, context["decision"]))
    return verify_document_lock_review(
        root, decision, context, now=now, artifact_root=artifact_root
    )

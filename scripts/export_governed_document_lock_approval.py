from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MANIFEST_PATH = Path("config/governance/governed_document_lock_manifest.json")
DEFAULT_OUTPUT_DIR = Path("runtime/artifacts/repository_validation/governance")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_" for character in value.strip()
    ).strip("_")


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governed document lock manifest must be a JSON object")
    return payload


def _approval_record(payload: dict[str, Any], approval_id: str) -> dict[str, Any]:
    records = payload.get("approval_records")
    if not isinstance(records, list):
        raise ValueError("approval_records must be a JSON array")
    for item in records:
        if not isinstance(item, dict):
            continue
        if str(item.get("approval_id", "")).strip() == approval_id:
            return item
    raise ValueError(f"approval record not found: {approval_id}")


def _lock_entry_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = payload.get("locked_documents")
    if not isinstance(entries, list):
        raise ValueError("locked_documents must be a JSON array")
    index: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        relative = str(item.get("path", "")).strip()
        if relative:
            index[relative] = item
    return index


def build_approval_evidence(
    *,
    repository_root: Path,
    approval_id: str,
    manifest_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = repository_root / MANIFEST_PATH
    manifest = (
        manifest_payload
        if manifest_payload is not None
        else _load_manifest(manifest_path)
    )
    approval = _approval_record(manifest, approval_id)
    if approval.get("approval_status") != "APPROVED":
        raise ValueError("approval record must be APPROVED")
    if approval.get("written_owner_approval") is not True:
        raise ValueError("approval record must confirm written owner approval")
    approved_hashes = approval.get("approved_sha256")
    if not isinstance(approved_hashes, dict) or not approved_hashes:
        raise ValueError("approval record must include approved_sha256")
    lock_index = _lock_entry_index(manifest)
    approved_documents: list[dict[str, Any]] = []
    for relative, approved_sha256 in approved_hashes.items():
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("approved document path must be non-empty text")
        if not isinstance(approved_sha256, str) or len(approved_sha256) != 64:
            raise ValueError(f"approved document sha256 is invalid: {relative}")
        path = repository_root / relative
        document_present = path.is_file()
        current_sha256 = _sha256(path) if document_present else ""
        lock_entry = lock_index.get(relative)
        manifest_expected_hash = (
            str(lock_entry.get("expected_hash", "")).lower()
            if lock_entry is not None
            else ""
        )
        manifest_sha256 = (
            str(lock_entry.get("sha256", "")).lower() if lock_entry is not None else ""
        )
        lock_state = (
            str(lock_entry.get("lock_state", "")) if lock_entry is not None else ""
        )
        approved_documents.append(
            {
                "path": relative,
                "approved_sha256": approved_sha256.lower(),
                "document_presence_status": (
                    "PRESENT" if document_present else "MISSING"
                ),
                "current_sha256": current_sha256,
                "manifest_entry_status": (
                    "REGISTERED" if lock_entry is not None else "MISSING"
                ),
                "manifest_expected_hash": manifest_expected_hash,
                "manifest_sha256": manifest_sha256,
                "lock_state": lock_state,
                "hash_matches_current_content": (
                    document_present and current_sha256 == approved_sha256.lower()
                ),
                "hash_matches_manifest_entry": (
                    lock_entry is not None
                    and manifest_sha256 == approved_sha256.lower()
                    and manifest_expected_hash == approved_sha256.lower()
                ),
            }
        )
    all_hashes_match = all(
        item["hash_matches_current_content"] and item["hash_matches_manifest_entry"]
        for item in approved_documents
    )
    generated_at_utc = datetime.now(UTC).replace(microsecond=0).isoformat()
    return {
        "schema_version": "1.0.0",
        "artifact_origin": "governed_document_lock_written_owner_approval",
        "generated_at_utc": generated_at_utc.replace("+00:00", "Z"),
        "repository_root": str(repository_root.resolve()),
        "manifest_path": MANIFEST_PATH.as_posix(),
        "approval_id": str(approval.get("approval_id", "")).strip(),
        "approval_scope": str(approval.get("approval_scope", "")).strip(),
        "approval_status": str(approval.get("approval_status", "")).strip(),
        "approved_by": str(approval.get("approved_by", "")).strip(),
        "approved_at_utc": str(approval.get("approved_at_utc", "")).strip(),
        "written_owner_approval": True,
        "approved_sha256": {
            str(path): str(sha256).lower() for path, sha256 in approved_hashes.items()
        },
        "approved_documents": approved_documents,
        "verification_status": "VERIFIED",
        "current_alignment_status": (
            "VERIFIED" if all_hashes_match else "RUNNING_WITH_BLOCKERS"
        ),
        "verification_summary": {
            "approved_document_count": len(approved_documents),
            "all_hashes_match": all_hashes_match,
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _load_bound_evidence(
    *,
    repository_root: Path,
    approval: dict[str, Any],
    output_path: Path,
) -> dict[str, Any] | None:
    evidence_path = str(approval.get("approval_evidence_path", "")).strip()
    evidence_sha256 = str(approval.get("approval_evidence_sha256", "")).strip().lower()
    if not evidence_path and not evidence_sha256:
        return None
    if not evidence_path or not evidence_sha256:
        raise ValueError("BOUND_APPROVAL_EVIDENCE_REFERENCE_INCOMPLETE")
    relative = PurePosixPath(evidence_path)
    if (
        relative.is_absolute()
        or PureWindowsPath(evidence_path).is_absolute()
        or "\\" in evidence_path
        or ".." in relative.parts
    ):
        raise ValueError("BOUND_APPROVAL_EVIDENCE_PATH_INVALID")
    if _SHA256_PATTERN.fullmatch(evidence_sha256) is None:
        raise ValueError("BOUND_APPROVAL_EVIDENCE_SHA256_INVALID")
    bound_path = (repository_root / evidence_path).resolve()
    if output_path.resolve() != bound_path:
        raise ValueError("BOUND_APPROVAL_EVIDENCE_PATH_OVERRIDE_BLOCKED")
    if not bound_path.is_file():
        raise ValueError("BOUND_APPROVAL_EVIDENCE_MISSING")
    if _sha256(bound_path) != evidence_sha256:
        raise ValueError("BOUND_APPROVAL_EVIDENCE_IMMUTABLE_MISMATCH")
    payload = _load_manifest(bound_path)
    if (
        payload.get("artifact_origin")
        != "governed_document_lock_written_owner_approval"
    ):
        raise ValueError("BOUND_APPROVAL_EVIDENCE_ORIGIN_INVALID")
    if (
        str(payload.get("approval_id", "")).strip()
        != str(approval.get("approval_id", "")).strip()
    ):
        raise ValueError("BOUND_APPROVAL_EVIDENCE_ID_MISMATCH")
    return payload


def persist_approval_evidence(
    *,
    repository_root: Path,
    approval_id: str,
    output_path: Path,
    manifest_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = (
        manifest_payload
        if manifest_payload is not None
        else _load_manifest(repository_root / MANIFEST_PATH)
    )
    approval = _approval_record(manifest, approval_id)
    bound = _load_bound_evidence(
        repository_root=repository_root,
        approval=approval,
        output_path=output_path,
    )
    if bound is not None:
        return bound
    payload = build_approval_evidence(
        repository_root=repository_root,
        approval_id=approval_id,
        manifest_payload=manifest,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export a verified governed document lock approval evidence artifact."
        )
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args(argv)

    repository_root = Path(args.repository_root).resolve()
    if args.output_path:
        output_path = Path(args.output_path)
        if not output_path.is_absolute():
            output_path = (repository_root / output_path).resolve()
    else:
        output_path = (
            repository_root
            / DEFAULT_OUTPUT_DIR
            / f"governed_document_lock_approval_{_slug(args.approval_id)}.json"
        )
    payload = persist_approval_evidence(
        repository_root=repository_root,
        approval_id=args.approval_id,
        output_path=output_path,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

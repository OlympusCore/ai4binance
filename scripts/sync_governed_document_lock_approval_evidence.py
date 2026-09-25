from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from export_governed_document_lock_approval import (
    DEFAULT_OUTPUT_DIR,
    MANIFEST_PATH,
    _load_manifest,
    _sha256,
    _slug,
    persist_approval_evidence,
)


def _approval_id(item: dict[str, Any]) -> str:
    approval_id = str(item.get("approval_id", "")).strip()
    if not approval_id:
        raise ValueError("approval record approval_id must be non-empty")
    return approval_id


def _canonical_record_copy(item: dict[str, Any]) -> dict[str, Any]:
    record = json.loads(json.dumps(item))
    if not isinstance(record, dict):
        raise ValueError("approval record entries must be JSON objects")
    record["approval_status"] = str(record.get("approval_status") or "APPROVED")
    record["written_owner_approval"] = True
    return record


def _output_path(repository_root: Path, approval_id: str) -> Path:
    return (
        repository_root
        / DEFAULT_OUTPUT_DIR
        / f"governed_document_lock_approval_{_slug(approval_id)}.json"
    )


def _attach_evidence_ref(
    records: list[dict[str, Any]],
    *,
    approval_id: str,
    evidence_path: str,
    evidence_sha256: str,
) -> None:
    for record in records:
        if str(record.get("approval_id", "")).strip() != approval_id:
            continue
        record["approval_evidence_path"] = evidence_path
        record["approval_evidence_sha256"] = evidence_sha256


def _normalize_legacy_written_owner_approvals(
    approval_records: list[dict[str, Any]],
    written_owner_approvals: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if written_owner_approvals is None:
        return None
    record_index: dict[str, dict[str, Any]] = {}
    for item in approval_records:
        if not isinstance(item, dict):
            raise ValueError("approval record entries must be JSON objects")
        record_index[_approval_id(item)] = item
    normalized_written: list[dict[str, Any]] = []
    for item in written_owner_approvals:
        if not isinstance(item, dict):
            raise ValueError("written_owner_approvals entries must be JSON objects")
        approval_id = _approval_id(item)
        if approval_id not in record_index:
            canonical_record = _canonical_record_copy(item)
            approval_records.append(canonical_record)
            record_index[approval_id] = canonical_record
        normalized_written.append(_canonical_record_copy(record_index[approval_id]))
    return normalized_written


def sync_manifest(
    *,
    repository_root: Path,
) -> dict[str, Any]:
    manifest_path = repository_root / MANIFEST_PATH
    manifest = _load_manifest(manifest_path)
    approval_records = manifest.get("approval_records")
    if not isinstance(approval_records, list):
        raise ValueError("approval_records must be a JSON array")
    written_owner_approvals = manifest.get("written_owner_approvals")
    if written_owner_approvals is not None and not isinstance(
        written_owner_approvals,
        list,
    ):
        raise ValueError("written_owner_approvals must be a JSON array when present")
    normalized_written_owner_approvals = _normalize_legacy_written_owner_approvals(
        approval_records,
        written_owner_approvals,
    )
    if normalized_written_owner_approvals is not None:
        manifest["written_owner_approvals"] = normalized_written_owner_approvals
        written_owner_approvals = normalized_written_owner_approvals
    exported: list[dict[str, Any]] = []
    for item in approval_records:
        if not isinstance(item, dict):
            raise ValueError("approval record entries must be JSON objects")
        approval_id = _approval_id(item)
        output_path = _output_path(repository_root, approval_id)
        payload = persist_approval_evidence(
            repository_root=repository_root,
            approval_id=approval_id,
            output_path=output_path,
            manifest_payload=manifest,
        )
        relative_output_path = output_path.relative_to(repository_root).as_posix()
        evidence_sha256 = _sha256(output_path)
        _attach_evidence_ref(
            approval_records,
            approval_id=approval_id,
            evidence_path=relative_output_path,
            evidence_sha256=evidence_sha256,
        )
        if isinstance(written_owner_approvals, list):
            _attach_evidence_ref(
                written_owner_approvals,
                approval_id=approval_id,
                evidence_path=relative_output_path,
                evidence_sha256=evidence_sha256,
            )
        exported.append(
            {
                "approval_id": approval_id,
                "approval_evidence_path": relative_output_path,
                "approval_evidence_sha256": evidence_sha256,
                "current_alignment_status": payload["current_alignment_status"],
            }
        )

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "schema_version": "1.0.0",
        "artifact_origin": "governed_document_lock_approval_evidence_sync",
        "manifest_path": MANIFEST_PATH.as_posix(),
        "approval_record_count": len(approval_records),
        "exported": exported,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export evidence artifacts for all governed document lock approvals "
            "and attach their references to the manifest."
        )
    )
    parser.add_argument("--repository-root", required=True)
    args = parser.parse_args(argv)

    repository_root = Path(args.repository_root).resolve()
    payload = sync_manifest(repository_root=repository_root)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

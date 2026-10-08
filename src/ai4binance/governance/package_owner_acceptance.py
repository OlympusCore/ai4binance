"""Recognize one reviewed owner amendment through the existing document chain."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ai4binance.governance.document_lock_authority import (
    CONTEXT_PATH,
    prospective_document_approvals,
)
from ai4binance.governance.governance_enforcement_fabric import (
    FABRIC_PATH,
    load_governance_enforcement_fabric,
)
from ai4binance.governance.repository_validator import read_verified_governed_document
from ai4binance.schema_validation import validate_local_definition

if TYPE_CHECKING:
    from ai4binance.enterprise.contracts import ApprovalRecord

CORE = "docs/governance/framework_core_vnext_governance.md"
MANIFEST = "config/governance/governed_document_lock_manifest.json"
RULE = "AI4B-GOV-C3-OWNER-20261007"
PROFILE = "BOUNDED_OWNER_PACKAGE"
PRIOR_CORE_SHA256 = "f9c25e829035791b2197f5bdb01e853152d6bdf83675af79489de2ad7df2563b"


@dataclass(frozen=True, slots=True)
class PackageOwnerAcceptance:
    """An eligible package still requires its exact current approval and evidence."""

    owner_person_id: str
    approver_id: str
    principal_id: str
    approver_role: str
    expires_at: datetime

    def record_blockers(self, record: ApprovalRecord) -> tuple[str, ...]:
        if (
            record.approver_id != self.approver_id
            or record.principal_id != self.principal_id
            or record.approver_role != self.approver_role
            or record.execution_allowed
            or record.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or record.research_confirmation is not None
            or record.expires_at is None
            or record.expires_at > self.expires_at
        ):
            return (f"BOUNDED_OWNER_RECORD_INELIGIBLE:{record.approval_id}",)
        return ()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("BOUNDED_OWNER_OBJECT_REQUIRED")
    return value


def _contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError("BOUNDED_OWNER_PATH_OUTSIDE_ROOT")
    return path


def _bound(root: Path, reference: dict[str, Any]) -> bytes:
    raw = _contained(root, reference["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("BOUNDED_OWNER_ARTIFACT_DRIFT")
    return raw


def _time(value: str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("BOUNDED_OWNER_TIMESTAMP_WITHOUT_ZONE")
    return instant.astimezone(UTC)


def _git(root: Path, *arguments: str) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("BOUNDED_OWNER_GIT_UNAVAILABLE")
    return subprocess.run(  # noqa: S603  # nosec B603
        (executable, "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout


def _installed_decision(
    root: Path, policy: dict[str, Any], now: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Application, normative recognition and final acceptance remain distinct."""
    manifest = _object(root / MANIFEST)
    _, error = prospective_document_approvals(root, manifest)
    if error is not None:
        raise ValueError("BOUNDED_OWNER_INSTALLATION_UNVERIFIED")
    context = _object(root / CONTEXT_PATH)
    decision = _object(_contained(root, policy["normative_decision_ref"]))
    validate_local_definition(
        root / "schemas/governance/governance_enforcement_fabric.schema.json",
        "bounded_owner_normative_decision",
        decision,
    )
    if (
        context["contract_version"] != "DocumentLockAuthorityContext/v4"
        or context["grant"] != decision["grant"]
        or context["subject_sha256"] != decision["subject_sha256"]
        or context["owner_person_id"] != policy["owner_person_id"]
        or decision["owner_person_id"] != policy["owner_person_id"]
    ):
        raise ValueError("BOUNDED_OWNER_DECISION_SUBJECT_MISMATCH")
    grant = json.loads(_bound(root, context["grant"]))
    reviewed = grant["review_subject"]
    if reviewed["epoch_id"] != policy["epoch_id"]:
        raise ValueError("BOUNDED_OWNER_DECISION_EPOCH_MISMATCH")
    core_documents = [
        document for document in reviewed["documents"] if document["path"] == CORE
    ]
    if len(core_documents) != 1:
        raise ValueError("BOUNDED_OWNER_EXACT_AMENDMENT_REQUIRED")
    core_document = core_documents[0]
    if (
        reviewed["baseline_commit"] != policy["review_baseline_commit"]
        or core_document["before_sha256"] != PRIOR_CORE_SHA256
        or core_document["before_version"] != "2.0.13"
        or core_document["version"] != "2.0.14"
        or core_document["sha256"] != policy["core_sha256"]
    ):
        raise ValueError("BOUNDED_OWNER_EXACT_AMENDMENT_REQUIRED")
    if decision["source"] != grant["source"]:
        raise ValueError("BOUNDED_OWNER_DECISION_SOURCE_MISMATCH")
    _bound(root, decision["source"])
    issued = _time(decision["issued_at_utc"])
    expires = _time(decision["expires_at_utc"])
    if (
        decision["revoked_at_utc"] is not None
        or not issued <= now < expires
        or expires - issued > timedelta(hours=24)
        or issued < _time(grant["issued_at_utc"])
        or expires > _time(grant["expires_at_utc"])
    ):
        raise ValueError("BOUNDED_OWNER_DECISION_NOT_CURRENT")
    evidence = json.loads(_bound(root, grant["review_subject"]["evidence"]))
    if not isinstance(evidence.get("reviewed_output_hashes"), dict):
        raise ValueError("BOUNDED_OWNER_REVIEWED_OUTPUTS_MISSING")
    return decision, evidence["reviewed_output_hashes"]


def _reviewed_outputs(
    root: Path, policy: dict[str, Any], outputs: dict[str, str]
) -> None:
    if set(outputs) != set(policy["reviewed_output_paths"]):
        raise ValueError("BOUNDED_OWNER_OUTPUT_SCOPE_MISMATCH")
    for relative, digest in outputs.items():
        raw = _contained(root, relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("BOUNDED_OWNER_OUTPUT_DRIFT:" + relative)
    absent = set(policy["allowed_change_paths"]) - set(outputs) - {MANIFEST}
    if any((root / relative).exists() for relative in absent):
        raise ValueError("BOUNDED_OWNER_ABSENT_PATH_RECREATED")
    _git(root, "merge-base", "--is-ancestor", policy["package_commit"], "HEAD")
    patch = _git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--no-textconv",
        policy["package_base_commit"],
        policy["package_commit"],
    )
    if hashlib.sha256(patch).hexdigest() != policy["package_patch_sha256"]:
        raise ValueError("BOUNDED_OWNER_ORIGINAL_PACKAGE_DRIFT")


def load_package_owner_acceptance(
    root: Path,
    changed_paths: tuple[str, ...],
    change_class: str,
    *,
    now: datetime | None = None,
) -> PackageOwnerAcceptance | None:
    """Keep legacy defaults outside the explicitly owner-reviewed C3 package."""
    if change_class != "C3_GOVERNED" or not changed_paths:
        return None
    path = root / FABRIC_PATH
    if not path.exists():
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("BOUNDED_OWNER_FABRIC_OBJECT_REQUIRED")
    policy = payload.get("bounded_owner_acceptance")
    if policy is None:
        return None
    load_governance_enforcement_fabric(root)
    if not set(changed_paths).issubset(policy["allowed_change_paths"]):
        return None
    core = read_verified_governed_document(root, CORE)
    if (
        policy["rule_id"] != RULE
        or RULE not in core
        or hashlib.sha256((root / CORE).read_bytes()).hexdigest()
        != policy["core_sha256"]
        or root.resolve() != Path(policy["canonical_root"]).resolve()
    ):
        raise ValueError("BOUNDED_OWNER_CORE_AUTHORITY_MISMATCH")
    decision, outputs = _installed_decision(root, policy, now or datetime.now(UTC))
    _reviewed_outputs(root, policy, outputs)
    return PackageOwnerAcceptance(
        policy["owner_person_id"],
        policy["approver_id"],
        policy["principal_id"],
        policy["approver_role"],
        _time(decision["expires_at_utc"]),
    )

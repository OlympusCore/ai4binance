"""Review prospective grant bindings without adopting them as lock authority."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ai4binance.governance import document_lock_review as review
from ai4binance.schema_validation import validate_local_definition

SCHEMA = review.SCHEMA.with_name("document_lock_grant_review.schema.json")
CONTEXT = "DocumentLockGrantReviewContext/v1"
MANIFEST_FIELD = "prospective_lock_grant"


def _grant_subject(
    grant: dict[str, Any], decision: dict[str, Any], context: dict[str, Any]
) -> None:
    subject = decision["review_subject"]
    expected = {
        "owner_person_id": decision["owner_person_id"],
        "subject_sha256": decision["subject_sha256"],
        "repository_root": subject["repository_root"],
        "epoch_id": subject["epoch_id"],
        "review_decision": context["decision"],
    }
    if any(grant[key] != value for key, value in expected.items()):
        raise ValueError("DOCUMENT_GRANT_SUBJECT_MISMATCH")
    if not grant["grant_id"].strip():
        raise ValueError("DOCUMENT_GRANT_ID_REQUIRED")
    if not (
        review._time(subject["issued_at_utc"])
        <= review._time(grant["issued_at_utc"])
        <= review._time(grant["not_before_utc"])
        < review._time(grant["expires_at_utc"])
        <= review._time(subject["expires_at_utc"])
    ):
        raise ValueError("DOCUMENT_GRANT_PERIOD_OUTSIDE_REVIEW")


def _manifest(root: Path, context: dict[str, Any], subject: dict[str, Any]) -> None:
    proposed = review._decode(review._bound_bytes(root, context["proposed_manifest"]))
    projection = review._decode(
        review._bound_bytes(root, subject["registration_manifest"])
    )
    expected = {
        **projection,
        MANIFEST_FIELD: {
            "contract_version": "DocumentLockRegistrationReview/v1",
            "grant": context["grant"],
        },
    }
    if proposed != expected:
        raise ValueError("DOCUMENT_GRANT_MANIFEST_SCOPE_MISMATCH")


def review_grant_files(
    root: Path,
    context: dict[str, Any],
    *,
    now: datetime,
    artifact_root: Path | None = None,
) -> dict[str, object]:
    """Consume external pins without granting authority."""
    validate_local_definition(SCHEMA, "context", context)
    root = root.resolve(strict=True)
    source_root = artifact_root.resolve(strict=True) if artifact_root else root
    revised = context["contract_version"] == "DocumentLockGrantReviewContext/v2"
    prior = review._decode(review._bound_bytes(source_root, context["review_context"]))
    validate_local_definition(review.SCHEMA, "context", prior)
    if revised != (prior["contract_version"] == "DocumentLockReviewContext/v2"):
        raise ValueError("DOCUMENT_GRANT_REVIEW_VERSION")
    decision = review._decode(review._bound_bytes(source_root, prior["decision"]))
    result = review.verify_document_lock_review(
        root, decision, prior, now=now, artifact_root=artifact_root
    )
    grant = review._decode(review._bound_bytes(source_root, context["grant"]))
    validate_local_definition(SCHEMA, "grant", grant)
    review._period(grant, now)
    _grant_subject(grant, decision, prior)
    # Reuse the same scoped revocation snapshot, checking both decision IDs.
    review._revocations(
        source_root, prior, {**decision, "decision_id": grant["grant_id"]}, now
    )
    for field in ("source", "baseline_replacement", "authority_procedure"):
        review._bound_bytes(source_root, grant[field])
    _manifest(source_root, context, decision["review_subject"])
    return {
        **result,
        "grant_status": "GRANT_BINDINGS_VALID",
        "grant_contract_version": grant["contract_version"],
        "grant_id": grant["grant_id"],
        "record_origin": grant["record_origin"],
        "proposed_manifest_sha256": context["proposed_manifest"]["sha256"],
        "authority_procedure_adopted": False,
        "lock_authority_recognized": False,
        "source_authentication": "NOT_VERIFIED",
        "required_authority": "SEPARATELY_ADOPTED_PROSPECTIVE_LOCK_CONTRACT",
    }

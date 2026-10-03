"""Consume explicit prospective owner authority; never write or activate it."""

from __future__ import annotations

import subprocess  # nosec B404
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai4binance.governance import document_lock_review as review
from ai4binance.schema_validation import validate_local_definition

SCHEMA = review.SCHEMA.with_name("document_lock_authority.schema.json")
CONTEXT_PATH = "runtime/artifacts/governance/document-lock/authority-context.json"
MANIFEST_CONTRACT = "DocumentLockRegistration/v1"
COMPLETED_MANIFEST_CONTRACT = "DocumentLockRegistration/v2"
OWNER_RECORD_ORIGIN = "OWNER_ISSUED"
INSTALLATION_RECORD_ORIGIN = "OPERATIONAL_INSTALLATION"
PROCEDURE_PATHS = (
    "docs/governance/framework_core_vnext_governance.md",
    "docs/governance/policy_manifest_governance.md",
    "schemas/governance/document_lock_authority.schema.json",
    "src/ai4binance/governance/document_lock_authority.py",
)
_INPUT: ContextVar[tuple[Path, Path] | None] = ContextVar(
    "document_lock_authority_input", default=None
)


@contextmanager
def authority_input(root: Path, context_path: Path) -> Iterator[None]:
    """Scope an operator-supplied context without changing acceptance rules."""
    token = _INPUT.set((root.resolve(), context_path.resolve()))
    try:
        yield
    finally:
        _INPUT.reset(token)


def _period_within(
    value: dict[str, Any], parent: dict[str, Any], now: datetime
) -> None:
    review._period(value, now)
    start = review._time(value["issued_at_utc"])
    end = review._time(value["expires_at_utc"])
    if not (
        review._time(parent["issued_at_utc"]) <= start
        and end <= review._time(parent["expires_at_utc"])
        and end - start <= timedelta(hours=24)
    ):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_PERIOD")


def _record(
    root: Path,
    context: dict[str, Any],
    key: str,
    subject: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    value = review._decode(review._bound_bytes(root, context[key]))
    validate_local_definition(SCHEMA, key, value)
    _period_within(value, subject, now)
    for field in ("owner_person_id", "repository_root", "epoch_id", "subject_sha256"):
        if value[field] != context[field]:
            raise ValueError("DOCUMENT_LOCK_AUTHORITY_SUBJECT")
    if value["record_origin"] != OWNER_RECORD_ORIGIN:
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_ORIGIN")
    review._bound_bytes(root, value["source"])
    return value


def _custody(
    context: dict[str, Any],
    adoption: dict[str, Any],
    grant: dict[str, Any],
    now: datetime,
) -> None:
    custody = context["custody"]
    if (
        custody["custodian_person_id"] != context["owner_person_id"]
        or custody["adoption_source"] != adoption["source"]
        or custody["grant_source"] != grant["source"]
        or not custody["decision_channel"].strip()
    ):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_CUSTODY")
    checked = review._time(custody["checked_at_utc"])
    if (
        not max(
            review._time(adoption["issued_at_utc"]),
            review._time(grant["issued_at_utc"]),
        )
        <= checked
        <= now
        < checked + timedelta(hours=24)
    ):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_CUSTODY_STALE")


def _procedure(root: Path, adoption: dict[str, Any]) -> None:
    references = adoption["procedure"]
    if sorted(r["path"] for r in references) != sorted(PROCEDURE_PATHS):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_PROCEDURE_SCOPE")
    for reference in references:
        review._bound_bytes(root, reference)


def _grant_scope(
    context: dict[str, Any],
    grant: dict[str, Any],
    subject: dict[str, Any],
) -> None:
    if (
        grant["adoption"] != context["adoption"]
        or grant["documents"] != subject["documents"]
        or grant["registration_manifest"] != subject["registration_manifest"]
    ):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_GRANT_SCOPE")


def _manifest(
    root: Path,
    payload: dict[str, Any],
    context: dict[str, Any],
    subject: dict[str, Any],
) -> None:
    actual = root / "config/governance/governed_document_lock_manifest.json"
    pinned = review._bound_bytes(root, context["final_manifest"])
    if actual.read_bytes() != pinned or review._decode(pinned) != payload:
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_MANIFEST_BYTES")
    expected = review._decode(
        review._bound_bytes(root, subject["registration_manifest"])
    )
    expected["prospective_lock_grant"] = {
        "contract_version": (
            COMPLETED_MANIFEST_CONTRACT
            if context["contract_version"]
            in {
                "DocumentLockAuthorityContext/v2",
                "DocumentLockAuthorityContext/v3",
            }
            else MANIFEST_CONTRACT
        ),
        "adoption": context["adoption"],
        "grant": context["grant"],
    }
    if payload != expected:
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_MANIFEST_SCOPE")


def verify_lock_authority(
    root: Path,
    payload: dict[str, Any],
    context: dict[str, Any],
    *,
    now: datetime,
) -> frozenset[tuple[str, str]]:
    """Recognize bounded authority without authenticating custody assertions."""
    completed = context.get("contract_version") in {
        "DocumentLockAuthorityContext/v2",
        "DocumentLockAuthorityContext/v3",
    }
    validate_local_definition(
        SCHEMA, "completed_context" if completed else "context", context
    )
    root = root.resolve(strict=True)
    if context["repository_root"] != root.as_posix():
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_ROOT")
    operation_time = _completion_time(root, context, now) if completed else now
    prior = review._decode(review._bound_bytes(root, context["review_context"]))
    validate_local_definition(review.SCHEMA, "context", prior)
    decision = review._decode(review._bound_bytes(root, prior["decision"]))
    review.verify_document_lock_review(root, decision, prior, now=operation_time)
    subject = decision["review_subject"]
    _context_subject(context, decision, operation_time)
    adoption = _record(root, context, "adoption", subject, operation_time)
    grant = _record(root, context, "grant", subject, operation_time)
    _period_within(grant, adoption, operation_time)
    _custody(context, adoption, grant, operation_time)
    _procedure(root, adoption)
    _grant_scope(context, grant, subject)
    _revocation_freshness(root, prior, context, adoption, grant, operation_time)
    _revocations(root, prior, decision, adoption, grant, operation_time)
    _manifest(root, payload, context, subject)
    if completed:
        _completed_installation(root, context, subject, now)
    return frozenset((doc["path"], doc["sha256"]) for doc in subject["documents"])


def _completion_time(root: Path, context: dict[str, Any], now: datetime) -> datetime:
    receipt = review._decode(review._bound_bytes(root, context["completion"]))
    validate_local_definition(SCHEMA, "completion", receipt)
    if (context["contract_version"] == "DocumentLockAuthorityContext/v3") != (
        receipt["contract_version"] == "DocumentLockCompletion/v2"
    ):
        raise ValueError("DOCUMENT_LOCK_COMPLETION_VERSION")
    completed_at = review._time(receipt["completed_at_utc"])
    if completed_at > now or receipt["record_origin"] != INSTALLATION_RECORD_ORIGIN:
        raise ValueError("DOCUMENT_LOCK_COMPLETION_ORIGIN_OR_TIME")
    return completed_at


def _completed_installation(
    root: Path, context: dict[str, Any], subject: dict[str, Any], now: datetime
) -> None:
    receipt = review._decode(review._bound_bytes(root, context["completion"]))
    completed_at = review._time(receipt["completed_at_utc"])
    revised = context["contract_version"] == "DocumentLockAuthorityContext/v3"
    if not (
        receipt["repository_root"] == context["repository_root"]
        and receipt["epoch_id"] == context["epoch_id"]
        and receipt["subject_sha256"] == context["subject_sha256"]
        and receipt["adoption"] == context["adoption"]
        and receipt["grant"] == context["grant"]
        and receipt["final_manifest"] == context["final_manifest"]
        and (
            receipt["reviewed_tree"] == subject["expected_tree"]
            if revised
            else receipt["expected_tree"] == subject["expected_tree"]
        )
        and completed_at >= review._time(context["custody"]["checked_at_utc"])
        and completed_at <= now
    ):
        raise ValueError("DOCUMENT_LOCK_COMPLETION_BINDING")
    operation = review._decode(
        review._bound_bytes(root, receipt["application_receipt"])
    )
    validate_local_definition(SCHEMA, "application_receipt", operation)
    if revised != (
        operation["contract_version"] == "DocumentLockApplicationReceipt/v2"
    ):
        raise ValueError("DOCUMENT_LOCK_APPLICATION_VERSION")
    if (
        operation["repository_root"] != context["repository_root"]
        or operation["subject_sha256"] != context["subject_sha256"]
        or operation["completed_at_utc"] != receipt["completed_at_utc"]
        or operation["final_manifest"] != context["final_manifest"]
        or operation["expected_tree"] != receipt["expected_tree"]
        or (revised and operation["reviewed_tree"] != receipt["reviewed_tree"])
    ):
        raise ValueError("DOCUMENT_LOCK_COMPLETION_APPLICATION")


def _context_subject(
    context: dict[str, Any],
    decision: dict[str, Any],
    now: datetime,
) -> None:
    subject = decision["review_subject"]
    _period_within(context, subject, now)
    if (
        context["subject_sha256"] != decision["subject_sha256"]
        or context["owner_person_id"] != decision["owner_person_id"]
        or context["epoch_id"] != subject["epoch_id"]
    ):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_CONTEXT_SUBJECT")


def _revocation_freshness(
    root: Path,
    prior: dict[str, Any],
    context: dict[str, Any],
    adoption: dict[str, Any],
    grant: dict[str, Any],
    now: datetime,
) -> None:
    snapshot = review._decode(review._bound_bytes(root, prior["revocations"]))
    _period_within(snapshot, prior["review_subject"], now)
    as_of = review._time(snapshot["issued_at_utc"])
    issued = max(
        review._time(adoption["issued_at_utc"]),
        review._time(grant["issued_at_utc"]),
    )
    if not issued <= as_of <= review._time(context["custody"]["checked_at_utc"]):
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_REVOCATION_STALE")


def _revocations(
    root: Path,
    prior: dict[str, Any],
    decision: dict[str, Any],
    adoption: dict[str, Any],
    grant: dict[str, Any],
    now: datetime,
) -> None:
    if len({d["decision_id"] for d in (decision, adoption, grant)}) != 3:
        raise ValueError("DOCUMENT_LOCK_AUTHORITY_DISTINCT_RECORD_IDS")
    for record in (adoption, grant):
        review._revocations(root, prior, {**decision, **record}, now)


def prospective_document_approvals(
    root: Path,
    payload: dict[str, Any],
) -> tuple[frozenset[tuple[str, str]], str | None]:
    """Feed the existing manifest consumer, failing closed on any authority gap."""
    marker = payload.get("prospective_lock_grant")
    if marker is None and "prospective_lock_grant" not in payload:
        return frozenset(), None
    try:
        if not isinstance(marker, dict) or marker.get("contract_version") not in {
            MANIFEST_CONTRACT,
            COMPLETED_MANIFEST_CONTRACT,
        }:
            raise ValueError("DOCUMENT_GRANT_NOT_ADOPTED")
        selected = _INPUT.get()
        expected_root, context_path = selected or (
            root.resolve(),
            root / CONTEXT_PATH,
        )
        if expected_root != root.resolve():
            raise ValueError("DOCUMENT_LOCK_AUTHORITY_CONTEXT_ROOT")
        context = review._object(context_path)
        if (marker["contract_version"] == COMPLETED_MANIFEST_CONTRACT) != (
            context.get("contract_version")
            in {
                "DocumentLockAuthorityContext/v2",
                "DocumentLockAuthorityContext/v3",
            }
        ):
            raise ValueError("DOCUMENT_LOCK_AUTHORITY_CONTRACT_MISMATCH")
        return verify_lock_authority(
            root, payload, context, now=datetime.now(UTC)
        ), None
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        return frozenset(), f"Prospective document lock authority invalid: {exc}."

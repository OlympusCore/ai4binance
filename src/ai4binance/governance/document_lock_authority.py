"""Consume explicit prospective owner authority; never write or activate it."""

from __future__ import annotations

import json
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
UPDATE_CONTEXT = "DocumentLockAuthorityContext/v4"
UPDATE_MANIFEST = "DocumentLockRegistration/v3"
OWNER_RECORD_ORIGIN = "OWNER_ISSUED"
INSTALLATION_RECORD_ORIGIN = "OPERATIONAL_INSTALLATION"
PROCEDURE_PATHS = (
    "docs/governance/framework_core_vnext_governance.md",
    "docs/governance/policy_manifest_governance.md",
    "schemas/governance/document_lock_authority.schema.json",
    "src/ai4binance/governance/document_lock_authority.py",
)
UPDATE_PROCEDURE_PATHS = (
    *PROCEDURE_PATHS,
    "src/ai4binance/governance/document_lock_review.py",
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
    if (
        review._repository_bytes(root, actual.relative_to(root).as_posix()) != pinned
        or review._decode(pinned) != payload
    ):
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
    installed_tree = None
    if context["contract_version"] == "DocumentLockAuthorityContext/v3":
        completion = review._decode(review._bound_bytes(root, context["completion"]))
        installed_tree = completion["expected_tree"]
    review.verify_document_lock_review(
        root, decision, prior, now=operation_time, installed_tree=installed_tree
    )
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
        if (
            isinstance(marker, dict)
            and marker.get("contract_version") == UPDATE_MANIFEST
        ):
            selected = _INPUT.get()
            expected_root, context_path = selected or (
                root.resolve(),
                root / CONTEXT_PATH,
            )
            if expected_root != root.resolve():
                raise ValueError("DOCUMENT_LOCK_AUTHORITY_CONTEXT_ROOT")
            context = review._object(context_path)
            pairs, _ = _verify_update(root, payload, context, now=datetime.now(UTC))
            return pairs, None
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


def _historical_state(
    root: Path, reference: dict[str, Any], now: datetime, seen: frozenset[str]
) -> tuple[dict[str, Any], frozenset[tuple[str, str]], datetime]:
    """Validate an immutable predecessor; its grants cover only its own bytes."""
    context = review._decode(review._bound_bytes(root, reference))
    manifest = review._decode(review._bound_bytes(root, context["final_manifest"]))
    if context.get("contract_version") == UPDATE_CONTEXT:
        pairs, completed_at = _verify_update(
            root, manifest, context, now=now, seen=seen, current=False
        )
    elif context.get("contract_version") == "DocumentLockAuthorityContext/v3":
        prior = review._decode(review._bound_bytes(root, context["review_context"]))
        decision = review._decode(review._bound_bytes(root, prior["decision"]))
        completion = review._decode(review._bound_bytes(root, context["completion"]))
        commit = review._accepted_commit(
            root, decision["review_subject"], completion["expected_tree"]
        )
        with review.accepted_history(root, commit):
            pairs = verify_lock_authority(root, manifest, context, now=now)
        completed_at = review._time(completion["completed_at_utc"])
    else:
        raise ValueError("DOCUMENT_UPDATE_PREDECESSOR_NOT_COMPLETED")
    return manifest, pairs, completed_at


def _update_registration(
    root: Path, before: dict[str, Any], subject: dict[str, Any], *, current: bool
) -> dict[str, Any]:
    """Require an exact inventory-preserving version/hash-only amendment."""
    after = review._decode(review._bound_bytes(root, subject["registration_manifest"]))
    prior = {e["path"]: e for e in before["locked_documents"]}
    entries = {e["path"]: e for e in after["locked_documents"]}
    documents = {d["path"]: d for d in subject["documents"]}
    if (
        len(entries) != len(after["locked_documents"])
        or len(prior) != len(before["locked_documents"])
        or len(documents) != len(subject["documents"])
        or entries.keys() != prior.keys()
    ):
        raise ValueError("DOCUMENT_UPDATE_INVENTORY")
    changed = {p for p in prior if prior[p] != entries[p]}
    if changed != documents.keys():
        raise ValueError("DOCUMENT_UPDATE_SCOPE")
    for path, doc in documents.items():
        old, new = prior[path], entries[path]
        if any(
            old.get(k) != new.get(k)
            for k in old.keys() | new.keys()
            if k not in {"version", "sha256", "expected_hash"}
        ):
            raise ValueError("DOCUMENT_UPDATE_AUTHORITY_CHANGE")
        if (old["version"], old["sha256"], old["expected_hash"]) != (
            doc["before_version"],
            doc["before_sha256"],
            doc["before_sha256"],
        ):
            raise ValueError("DOCUMENT_UPDATE_PREDECESSOR_DOCUMENT")
        data = review._bound_bytes(root, doc["payload"])
        before_data = review._bound_bytes(root, doc["before_payload"])
        before_metadata = (
            review.read_document_frontmatter(root / doc["before_payload"]["path"]) or {}
        )
        metadata = review.read_document_frontmatter(root / doc["payload"]["path"]) or {}
        if (
            review._digest(data) != doc["sha256"]
            or review._digest(before_data) != doc["before_sha256"]
            or {k: v for k, v in metadata.items() if k != "version"}
            != {k: v for k, v in before_metadata.items() if k != "version"}
            or (metadata.get("document_id"), metadata.get("version"))
            != (doc["document_id"], doc["version"])
            or (new["version"], new["sha256"], new["expected_hash"])
            != (doc["version"], doc["sha256"], doc["sha256"])
            or doc["before_version"] == doc["version"]
        ):
            raise ValueError("DOCUMENT_UPDATE_DOCUMENT_BINDING")
        if current and review._repository_bytes(root, path) != data:
            raise ValueError("DOCUMENT_UPDATE_CURRENT_DOCUMENT_DRIFT")
    if {k: v for k, v in before.items() if k != "locked_documents"} != {
        k: v for k, v in after.items() if k != "locked_documents"
    }:
        raise ValueError("DOCUMENT_UPDATE_HISTORY_OR_POLICY_CHANGE")
    return after


def _update_procedure(root: Path, subject: dict[str, Any], *, current: bool) -> None:
    references = subject["procedure"]
    if sorted(r["path"] for r in references) != sorted(UPDATE_PROCEDURE_PATHS):
        raise ValueError("DOCUMENT_UPDATE_PROCEDURE_SCOPE")
    for ref in references:
        data = review._bound_bytes(root, ref["source"])
        if review._digest(data) != ref["sha256"]:
            raise ValueError("DOCUMENT_UPDATE_PROCEDURE_BINDING")
        if current and review._repository_bytes(root, ref["path"]) != data:
            raise ValueError("DOCUMENT_UPDATE_CURRENT_PROCEDURE_DRIFT")
    for key in ("patch", "evidence", "rollback"):
        review._bound_bytes(root, subject[key])


def _update_grant(root: Path, context: dict[str, Any]) -> dict[str, Any]:
    """Require a genuinely issued decision over this exact update subject."""
    grant = review._decode(review._bound_bytes(root, context["grant"]))
    validate_local_definition(SCHEMA, "update_grant", grant)
    subject = grant["review_subject"]
    if (
        grant["record_origin"] != OWNER_RECORD_ORIGIN
        or grant["revoked_at_utc"] is not None
        or context["owner_person_id"] != grant["owner_person_id"]
        or context["subject_sha256"] != grant["subject_sha256"]
        or subject["repository_root"] != root.as_posix()
        or subject["predecessor"] != context["predecessor"]
        or grant["custody"]["custodian_person_id"] != grant["owner_person_id"]
        or grant["custody"]["source"] != grant["source"]
        or not grant["custody"]["decision_channel"].strip()
    ):
        raise ValueError("DOCUMENT_UPDATE_OWNER_OR_SUBJECT")
    subject_hash = review._digest(
        json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
    )
    if subject_hash != grant["subject_sha256"]:
        raise ValueError("DOCUMENT_UPDATE_SUBJECT_HASH")
    review._bound_bytes(root, grant["source"])
    return grant


def _update_completion(
    root: Path, context: dict[str, Any], grant: dict[str, Any], now: datetime
) -> datetime:
    """Bind observed installation to a decision valid at application time."""
    completion = review._decode(review._bound_bytes(root, context["completion"]))
    validate_local_definition(SCHEMA, "update_completion", completion)
    completed_at = review._time(completion["completed_at_utc"])
    if completion["record_origin"] != INSTALLATION_RECORD_ORIGIN or completed_at > now:
        raise ValueError("DOCUMENT_UPDATE_COMPLETION_ORIGIN_OR_TIME")
    review._period(grant, completed_at)
    if not (
        review._time(grant["issued_at_utc"])
        <= review._time(grant["custody"]["checked_at_utc"])
        <= completed_at
    ):
        raise ValueError("DOCUMENT_UPDATE_CUSTODY_TIME")
    if review._time(grant["expires_at_utc"]) - review._time(
        grant["issued_at_utc"]
    ) > timedelta(hours=24):
        raise ValueError("DOCUMENT_UPDATE_PERIOD")
    for field in (
        "repository_root",
        "subject_sha256",
        "grant",
        "predecessor",
        "final_manifest",
    ):
        if completion[field] != context[field]:
            raise ValueError("DOCUMENT_UPDATE_COMPLETION_BINDING")
    return completed_at


def _update_revocations(
    root: Path, context: dict[str, Any], grant: dict[str, Any], completed_at: datetime
) -> None:
    """Reject revoked authority and an unbound installation-time snapshot."""
    subject = grant["review_subject"]
    revocations = review._decode(review._bound_bytes(root, context["revocations"]))
    validate_local_definition(review.SCHEMA, "revocations", revocations)
    review._period(revocations, completed_at)
    if (revocations["repository_root"], revocations["epoch_id"]) != (
        root.as_posix(),
        subject["epoch_id"],
    ):
        raise ValueError("DOCUMENT_UPDATE_REVOCATION_SCOPE")
    if (
        grant["decision_id"] in revocations["revoked_decision_ids"]
        or grant["owner_person_id"] in revocations["revoked_owner_ids"]
        or grant["subject_sha256"] in revocations["revoked_subjects"]
    ):
        raise ValueError("DOCUMENT_UPDATE_REVOKED")


def _verify_update(
    root: Path,
    payload: dict[str, Any],
    context: dict[str, Any],
    *,
    now: datetime,
    seen: frozenset[str] = frozenset(),
    current: bool = True,
) -> tuple[frozenset[tuple[str, str]], datetime]:
    """Recognize only a new owner-issued, completed, exact predecessor transition."""
    validate_local_definition(SCHEMA, "update_context", context)
    root = root.resolve(strict=True)
    if context["repository_root"] != root.as_posix():
        raise ValueError("DOCUMENT_UPDATE_ROOT")
    identity = context["grant"]["sha256"]
    if identity in seen or len(seen) >= 32:
        raise ValueError("DOCUMENT_UPDATE_CYCLE_OR_DEPTH")
    grant = _update_grant(root, context)
    subject = grant["review_subject"]
    completed_at = _update_completion(root, context, grant, now)
    before, pairs, prior_time = _historical_state(
        root, context["predecessor"], now, seen | {identity}
    )
    if prior_time > review._time(grant["issued_at_utc"]):
        raise ValueError("DOCUMENT_UPDATE_PREDECESSOR_TIME")
    predecessor = review._decode(review._bound_bytes(root, context["predecessor"]))
    if (
        subject["predecessor_manifest"] != predecessor["final_manifest"]
        or predecessor["owner_person_id"] != context["owner_person_id"]
    ):
        raise ValueError("DOCUMENT_UPDATE_PREDECESSOR_MANIFEST")
    adoption = predecessor["contract_version"] == "DocumentLockAuthorityContext/v3"
    expected_decision = (
        "ADOPT_SUCCESSOR_PROCEDURE_AND_APPLY" if adoption else "APPLY_DOCUMENT_UPDATE"
    )
    if grant["decision"] != expected_decision:
        raise ValueError("DOCUMENT_UPDATE_ADOPTION_REQUIRED")
    if current:
        if review._git_text(root, "rev-parse", "--show-toplevel") != root.as_posix():
            raise ValueError("DOCUMENT_UPDATE_ROOT")
        review._git_bytes(
            root, "merge-base", "--is-ancestor", subject["baseline_commit"], "HEAD"
        )
    _update_revocations(root, context, grant, completed_at)
    expected = _update_registration(root, before, subject, current=current)
    _update_procedure(root, subject, current=current)
    expected["prospective_lock_grant"] = {
        "contract_version": UPDATE_MANIFEST,
        "grant": context["grant"],
        "predecessor": context["predecessor"],
    }
    pinned = review._bound_bytes(root, context["final_manifest"])
    if payload != expected or review._decode(pinned) != expected:
        raise ValueError("DOCUMENT_UPDATE_MANIFEST_SCOPE")
    if (
        current
        and review._repository_bytes(
            root, "config/governance/governed_document_lock_manifest.json"
        )
        != pinned
    ):
        raise ValueError("DOCUMENT_UPDATE_CURRENT_MANIFEST_DRIFT")
    return pairs | frozenset(
        (d["path"], d["sha256"]) for d in subject["documents"]
    ), completed_at

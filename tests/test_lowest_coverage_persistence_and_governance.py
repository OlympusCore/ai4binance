"""Failure-path coverage for persistence and governance contract boundaries."""

# mypy: disable-error-code="arg-type,misc,attr-defined"

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.application.governance.memory_approval import (
    MemoryApprovalVerificationService,
    MemoryPromotionRequest,
)
from ai4binance.governance.audit_checkpoint import (
    AuditAnchorStatus,
    AuditChainCheckpoint,
    AuditRetentionDirective,
    checkpoint_audit_chain,
    verify_audit_checkpoint,
)
from ai4binance.governance.enforcement.contracts import EnforcementOutcome
from ai4binance.governance.enforcement.receipt import (
    PolicyEnforcementReceipt,
    PolicyEnforcementStatus,
    build_policy_enforcement_receipt,
)
from ai4binance.infrastructure.persistence import safe_json
from ai4binance.infrastructure.persistence.safe_json import (
    AuditEvent,
    DestinationVerificationError,
    JsonlAuditStore,
    SecretRedactor,
    VerifiedWriteResult,
    fail_verification,
    read_bounded_jsonl_tail,
    to_primitive,
    write_json_object_verified,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)
HASH = "a" * 64


def _retention() -> AuditRetentionDirective:
    return AuditRetentionDirective("OPERATIONS", date(2030, 1, 1), False, "governance")


def _checkpoint(**changes: object) -> AuditChainCheckpoint:
    payload: dict[str, object] = {
        "checkpoint_id": "checkpoint",
        "journal_ref": "journal",
        "journal_path_sha256": HASH,
        "chain_position": 1,
        "record_sha256": HASH,
        "created_at": NOW,
        "retention": _retention(),
    }
    payload.update(changes)
    return AuditChainCheckpoint(**payload)


def test_audit_checkpoint_contract_rejects_incomplete_anchor_and_authority() -> None:
    with pytest.raises(ValueError, match="class and authority"):
        AuditRetentionDirective("", None, False, "")
    with pytest.raises(ValueError, match="legal hold"):
        AuditRetentionDirective("KEEP", date(2030, 1, 1), True, "governance")
    assert _retention().to_payload()["retain_until"] == "2030-01-01"
    for changes, message in (
        ({"anchor_status": "LOCAL_ONLY"}, "anchor status"),
        ({"checkpoint_id": ""}, "identity"),
        ({"chain_position": 0}, "positive"),
        ({"record_sha256": "bad"}, "digest"),
        ({"created_at": datetime(2026, 1, 1)}, "UTC"),
        ({"external_anchor_ref": "ref"}, "binding"),
        ({"external_anchor_sha256": "b" * 64}, "binding"),
        (
            {"anchor_status": AuditAnchorStatus.EXTERNAL_ANCHOR_RECORDED},
            "requires reference",
        ),
        ({"external_anchor_ref": "ref", "external_anchor_sha256": HASH}, "local-only"),
        ({"execution_allowed": True}, "cannot grant"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_checkpoint(), **changes)
    external = _checkpoint(
        anchor_status=AuditAnchorStatus.EXTERNAL_ANCHOR_RECORDED,
        external_anchor_ref="anchor:1",
        external_anchor_sha256=HASH,
    )
    assert external.to_payload()["semantic_sha256"] == external.semantic_sha256
    with pytest.raises(ValueError, match="reference"):
        replace(external, external_anchor_ref=" ")


def test_checkpoint_creation_and_verification_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "journal.jsonl"
    record = {"chain_position": 1, "record_sha256": HASH}
    journal.write_text(json.dumps(record) + "\n", encoding="utf-8")
    store = SimpleNamespace(path=journal, verify_chain=lambda: HASH)
    checkpoint = checkpoint_audit_chain(
        cast(Any, store),
        checkpoint_id="checkpoint",
        journal_ref="journal",
        created_at=NOW,
        retention=_retention(),
    )
    assert checkpoint.chain_position == 1
    assert verify_audit_checkpoint(cast(Any, store), checkpoint)
    monkeypatch.setattr(
        "ai4binance.governance.audit_checkpoint._journal_path_sha256",
        lambda _store: "b" * 64,
    )
    assert not verify_audit_checkpoint(cast(Any, store), checkpoint)
    monkeypatch.undo()
    journal.write_text("not-json\n", encoding="utf-8")
    assert not verify_audit_checkpoint(cast(Any, store), checkpoint)
    from ai4binance.governance import audit_checkpoint

    for tail, _head, message in (
        ((), HASH, "at least one"),
        (b"not-json", HASH, "tail is invalid"),
        (json.dumps([]).encode(), HASH, "must be an object"),
        (json.dumps({}).encode(), HASH, "tamper-evident"),
        (
            json.dumps({"chain_position": 1, "record_sha256": "b" * 64}).encode(),
            HASH,
            "head mismatch",
        ),
    ):
        monkeypatch.setattr(
            audit_checkpoint,
            "read_bounded_jsonl_tail",
            lambda *_args, _tail=tail, **_kwargs: (_tail,) if _tail else (),
        )
        with pytest.raises(ValueError, match=message):
            checkpoint_audit_chain(
                cast(Any, store),
                checkpoint_id="checkpoint",
                journal_ref="journal",
                created_at=NOW,
                retention=_retention(),
            )
    changed = SimpleNamespace(
        path=journal, verify_chain=iter((HASH, "b" * 64)).__next__
    )
    monkeypatch.setattr(
        audit_checkpoint,
        "read_bounded_jsonl_tail",
        lambda *_args, **_kwargs: (json.dumps(record).encode(),),
    )
    with pytest.raises(ValueError, match="changed during"):
        checkpoint_audit_chain(
            cast(Any, changed),
            checkpoint_id="checkpoint",
            journal_ref="journal",
            created_at=NOW,
            retention=_retention(),
        )
    journal.write_text("\n", encoding="utf-8")
    assert not verify_audit_checkpoint(cast(Any, store), checkpoint)
    journal.write_text(json.dumps([]) + "\n", encoding="utf-8")
    assert not verify_audit_checkpoint(cast(Any, store), checkpoint)
    journal.write_text(
        json.dumps({"chain_position": 2, "record_sha256": HASH}) + "\n",
        encoding="utf-8",
    )
    assert not verify_audit_checkpoint(cast(Any, store), checkpoint)


def _receipt(**changes: object) -> PolicyEnforcementReceipt:
    payload: dict[str, object] = {
        "receipt_id": "receipt",
        "decision_id": "decision",
        "decision_sha256": HASH,
        "subject_hash": HASH,
        "scope_hash": HASH,
        "approval_set_hash": HASH,
        "pep_id": "pep",
        "enforcement_id": "enforcement",
        "enforced_at": NOW,
        "status": PolicyEnforcementStatus.DENIED,
        "blockers": ("DENIED",),
    }
    payload.update(changes)
    return PolicyEnforcementReceipt(**payload)


def test_policy_receipt_validates_all_authority_bindings() -> None:
    for changes, message in (
        ({"status": "DENIED"}, "status"),
        ({"receipt_id": ""}, "required"),
        ({"decision_sha256": "bad"}, "digest"),
        ({"enforced_at": datetime(2026, 1, 1)}, "UTC"),
        ({"blockers": ("",)}, "blanks"),
        ({"blockers": ("A", "A")}, "unique"),
        ({"capability_lease_id": "lease"}, "binding"),
        ({"outcome_sha256": "bad"}, "digest"),
        (
            {"status": PolicyEnforcementStatus.ENFORCED, "blockers": ()},
            "requires capability",
        ),
        ({"blockers": ()}, "requires blockers"),
        ({"execution_allowed": True}, "cannot grant"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_receipt(), **changes)
    enforced = _receipt(
        status=PolicyEnforcementStatus.ENFORCED,
        blockers=(),
        capability_lease_id="lease",
        capability_policy_hash=HASH,
        capability_scope_hash=HASH,
        capability_run_id="run",
        capability_project="project",
        capability_tool_name="tool",
        outcome_sha256=HASH,
    )
    assert enforced.to_payload()["semantic_sha256"] == enforced.semantic_sha256
    with pytest.raises(ValueError, match="lease_id"):
        replace(enforced, capability_lease_id="")
    with pytest.raises(ValueError, match="cannot contain blockers"):
        replace(enforced, blockers=("BLOCK",))


def test_policy_receipt_builder_denies_and_enforces_only_consumed_capabilities() -> (
    None
):
    decision = SimpleNamespace(
        scope_hash=HASH,
        decision_id="decision",
        object_hash=HASH,
        approval_set_hash=HASH,
        blockers=("BLOCKER",),
        reason_codes=(),
        outcome=EnforcementOutcome.DENY,
        evaluated_controls=(),
        policy_versions=(),
        evidence_hash=HASH,
        authority_snapshot_hash=HASH,
        enforcement_profile_version="v1",
        enforcement_profile_hash=HASH,
        blocker_snapshot_hash=HASH,
        audit_receipt_hash=HASH,
        consequence="NO_TRADE",
        replay_fingerprint=HASH,
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    denied = build_policy_enforcement_receipt(
        receipt_id="receipt",
        decision=cast(Any, decision),
        pep_id="pep",
        enforcement_id="enforcement",
        enforced_at=NOW,
    )
    assert denied.status is PolicyEnforcementStatus.DENIED
    decision.outcome = EnforcementOutcome.ALLOW
    with pytest.raises(PermissionError, match="CAPABILITY_REQUIRED"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
        )
    lease = SimpleNamespace(
        lease_id="lease",
        policy_hash=HASH,
        scope_hash=HASH,
        run_id="run",
        project="project",
        tool_name="tool",
        consumed_at=NOW,
        execution_id="enforcement",
    )
    store = SimpleNamespace(verify_consumed=lambda *_args, **_kwargs: None)
    with pytest.raises(PermissionError, match="CAPABILITY_STORE"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
        )
    lease.consumed_at = None
    with pytest.raises(PermissionError, match="NOT_CONSUMED"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
            capability_store=cast(Any, store),
        )
    lease.consumed_at = NOW
    lease.scope_hash = ""
    with pytest.raises(PermissionError, match="SCOPE_MISMATCH"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
            capability_store=cast(Any, store),
        )
    lease.scope_hash = HASH
    lease.policy_hash = "b" * 64
    with pytest.raises(PermissionError, match="POLICY_MISMATCH"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
            capability_store=cast(Any, store),
        )
    lease.policy_hash = HASH
    with pytest.raises(ValueError, match="outcome_sha256"):
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
            capability_store=cast(Any, store),
        )
    assert (
        build_policy_enforcement_receipt(
            receipt_id="receipt",
            decision=cast(Any, decision),
            pep_id="pep",
            enforcement_id="enforcement",
            enforced_at=NOW,
            capability_lease=cast(Any, lease),
            capability_store=cast(Any, store),
            outcome_sha256=HASH,
        ).status
        is PolicyEnforcementStatus.ENFORCED
    )


def _memory_request(**changes: object) -> MemoryPromotionRequest:
    record = SimpleNamespace(memory_id="memory", content_hash=HASH)
    candidate = SimpleNamespace(record=record, binding_sha256=HASH)
    approval = SimpleNamespace(
        status="APPROVED",
        revoked_at=None,
        expires_at=None,
        policy_version="policy",
        candidate_memory_id="memory",
        candidate_content_hash=HASH,
        approval_record_id="approval",
        approver_ref="approver",
        approved_at=NOW,
    )
    verification = SimpleNamespace(
        policy_version="policy",
        candidate_memory_id="memory",
        candidate_content_hash=HASH,
        approval_record_id="approval",
        verification_record_id="verification",
        status="VERIFIED",
        verifier_ref="verifier",
        verified_at=NOW,
    )
    payload: dict[str, object] = {
        "candidate": candidate,
        "approval_record": approval,
        "verification_record": verification,
        "requested_at": NOW,
        "policy_version": "policy",
    }
    payload.update(changes)
    return MemoryPromotionRequest(**payload)


def test_memory_approval_verification_collects_each_blocker() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _memory_request(requested_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="policy version"):
        _memory_request(policy_version="")
    request = _memory_request()
    assert MemoryApprovalVerificationService().verify(request).verified
    approval = request.approval_record
    verification = request.verification_record
    approval.status = "DENIED"
    approval.revoked_at = NOW
    approval.expires_at = NOW
    approval.policy_version = "other"
    approval.candidate_memory_id = "other"
    approval.candidate_content_hash = "b" * 64
    approval.approver_ref = "same"
    approval.approved_at = NOW.replace(year=2027)
    verification.policy_version = "other"
    verification.candidate_memory_id = "other"
    verification.candidate_content_hash = "c" * 64
    verification.approval_record_id = "other"
    verification.status = "INVALID"
    verification.verifier_ref = "same"
    verification.verified_at = NOW.replace(year=2028)
    result = MemoryApprovalVerificationService().verify(request)
    assert not result.verified
    assert "MEMORY_APPROVAL_NOT_APPROVED" in result.blockers
    assert "MEMORY_VERIFICATION_PRECEDES_APPROVAL" not in result.blockers


class _ExampleEnum(StrEnum):
    VALUE = "VALUE"


def test_safe_json_public_serialization_and_verification_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identity"):
        VerifiedWriteResult("", "", "VERIFIED")
    with pytest.raises(ValueError, match="operation"):
        VerifiedWriteResult("path", "subject", "VERIFIED", operation="")
    with pytest.raises(ValueError, match="cannot contain blockers"):
        VerifiedWriteResult("path", "subject", "VERIFIED", ("BLOCK",))
    with pytest.raises(ValueError, match="requires blockers"):
        VerifiedWriteResult("path", "subject", "VERIFICATION_FAILED")
    redactor = SecretRedactor()
    assert redactor.redact(
        {"api-key": "secret", "input_tokens": 1, "items": ({"token": "x"},)}
    ) == {
        "api-key": "[REDACTED]",
        "input_tokens": 1,
        "items": [{"token": "[REDACTED]"}],
    }
    with pytest.raises(ValueError, match="event_type"):
        AuditEvent("bad", NOW, {})
    with pytest.raises(ValueError, match="timezone"):
        AuditEvent("VALID_EVENT", datetime(2026, 1, 1), {})
    with pytest.raises(ValueError, match="snapshot"):
        AuditEvent("VALID_EVENT", NOW, {}, snapshot_id=" ")
    path = tmp_path / "state.json"
    result = write_json_object_verified(
        path, {"amount": "1"}, blocker="WRITE", indent=2, durable=True
    )
    assert result.status == "VERIFIED"
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert to_primitive(
        {
            "enum": _ExampleEnum.VALUE,
            "date": NOW.date(),
            "time": NOW,
            "set": {"b", "a"},
            "tuple": (Decimal("2"),),
        }
    ) == {
        "enum": "VALUE",
        "date": "2026-09-15",
        "time": NOW.isoformat(),
        "set": ["a", "b"],
        "tuple": ["2"],
    }
    with pytest.raises(TypeError, match="serializable"):
        to_primitive(object())
    assert fail_verification("BLOCK", destination=path, subject_id="subject").args == (
        "BLOCK",
    )


def test_safe_json_jsonl_boundaries_and_tamper_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="maximum JSONL"):
        JsonlAuditStore(tmp_path / "events", max_event_bytes=0)
    path = tmp_path / "events.jsonl"
    store = JsonlAuditStore(path, tamper_evident=True, max_event_bytes=8_192)
    event = AuditEvent("VALID_EVENT", NOW, {"secret": "hidden"}, snapshot_id="snapshot")
    assert store.append_verified(event).operation == "jsonl_append"
    assert store._verify_chain_state_unlocked()[1] == 2
    assert read_bounded_jsonl_tail(path, max_lines=1)
    with pytest.raises(ValueError, match="limits"):
        read_bounded_jsonl_tail(path, max_lines=0)
    with pytest.raises(OSError, match="bounded"):
        read_bounded_jsonl_tail(path, max_bytes=1)
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(OSError, match="no event"):
        store._read_last_nonempty_line()
    with pytest.raises(TypeError, match="objects"):
        store._seal_tamper_evident_record(
            [], previous_record_hash="GENESIS", chain_position=1
        )
    monkeypatch.setattr(
        safe_json, "_read_json_object", lambda *_args, **_kwargs: {"changed": True}
    )
    with pytest.raises(DestinationVerificationError, match="VERIFY"):
        write_json_object_verified(
            tmp_path / "changed.json", {"expected": True}, blocker="VERIFY"
        )
    normal = JsonlAuditStore(tmp_path / "normal.jsonl")
    assert normal._chain_state_or_fail(subject_id="subject") == ("GENESIS", 1)
    monkeypatch.setattr(
        JsonlAuditStore, "_last_event_unlocked", lambda _self: {"other": True}
    )
    with pytest.raises(DestinationVerificationError, match="DESTINATION"):
        normal.append_verified(AuditEvent("VALID_EVENT", NOW, {}))
    monkeypatch.undo()
    broken = JsonlAuditStore(tmp_path / "broken.jsonl", tamper_evident=True)
    broken.path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(DestinationVerificationError, match="CHAIN_INVALID"):
        broken._chain_state_or_fail(subject_id="subject")
    bounded = JsonlAuditStore(tmp_path / "bounded.jsonl", max_event_bytes=1)
    bounded.path.write_text("long-record\n", encoding="utf-8")
    with pytest.raises(OSError, match="bounded"):
        bounded._read_last_nonempty_line()
    for raw, message in ((b"[]", "JSON object"), (b"{", "Expecting")):
        with pytest.raises((ValueError, json.JSONDecodeError), match=message):
            safe_json._load_event_line(raw, label="line")
    with pytest.raises(ValueError, match="invalid"):
        safe_json._text_field({}, "hash", label="line")
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("not-json", encoding="utf-8")
    with pytest.raises(DestinationVerificationError, match="READ"):
        safe_json._read_json_object(invalid_json, blocker="READ")
    non_object = tmp_path / "array.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(DestinationVerificationError, match="READ"):
        safe_json._read_json_object(non_object, blocker="READ")


def test_safe_json_chain_rejects_each_invalid_seal_and_supports_posix_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chain.jsonl"
    store = JsonlAuditStore(path, tamper_evident=True)
    for payload, message in (
        ({}, "missing sealing"),
        ({"tamper_evident": True, "chain_position": 2}, "position is invalid"),
        (
            {
                "tamper_evident": True,
                "chain_position": 1,
                "previous_record_sha256": "wrong",
            },
            "hash chain",
        ),
        (
            {
                "tamper_evident": True,
                "chain_position": 1,
                "previous_record_sha256": "GENESIS",
                "event_sha256": "hash",
                "record_sha256": "hash",
            },
            "event hash invalid",
        ),
    ):
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            store._verify_chain_state_unlocked()
    sealed = store._seal_tamper_evident_record(
        {"event_type": "VALID_EVENT"}, previous_record_hash="GENESIS", chain_position=1
    )
    sealed["record_sha256"] = "wrong"
    path.write_text(json.dumps(sealed) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record hash invalid"):
        store._verify_chain_state_unlocked()
    empty = tmp_path / "empty.jsonl"
    empty.touch()
    assert read_bounded_jsonl_tail(empty) == ()
    long = JsonlAuditStore(tmp_path / "long.jsonl", max_event_bytes=100_000)
    long.path.write_bytes(b"x" * 70_000 + b"\n")
    assert long._read_last_nonempty_line() == b"x" * 70_000

    calls: list[tuple[int, int]] = []

    class Stream:
        def fileno(self) -> int:
            return 7

    fake_fcntl = SimpleNamespace(
        LOCK_EX=1,
        LOCK_UN=2,
        flock=lambda descriptor, operation: calls.append((descriptor, operation)),
    )
    monkeypatch.setattr(safe_json.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)
    stream = cast(Any, Stream())
    safe_json._acquire_file_lock(stream)
    safe_json._release_file_lock(stream)
    assert calls == [(7, 1), (7, 2)]

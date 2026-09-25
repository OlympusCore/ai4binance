"""Append-only audit storage and secret redaction tests."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import cast

import pytest

import ai4binance.storage.destination_verification as destination_verification
from ai4binance.infrastructure.persistence import safe_json
from ai4binance.storage import (
    AuditEvent,
    DestinationVerificationError,
    JsonlAuditStore,
    SecretRedactor,
    VerificationStatus,
    VerifiedWriteResult,
    read_bounded_jsonl_tail,
    write_json_object_verified,
)
from ai4binance.storage.destination_verification import read_json_object

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def test_chained_successor_preserves_legacy_and_reopens_idempotently(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "research.jsonl"
    legacy.write_text('{"historical":true}\n', encoding="utf-8")
    before = legacy.read_bytes()
    store = JsonlAuditStore.chained_successor(legacy)
    store.append(AuditEvent("RESEARCH_COMPLETED", NOW, {"safe": True}))
    head = store.verify_chain()
    assert legacy.read_bytes() == before
    reopened = JsonlAuditStore.chained_successor(legacy)
    assert reopened.verify_chain() == head
    rows = [json.loads(line) for line in store.path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["event_type"] == "LEGACY_AUDIT_ANCHOR"
    assert rows[0]["payload"]["historical_authenticity_verified"] is False
    assert rows[1]["previous_record_sha256"] == rows[0]["record_sha256"]
    legacy.write_text('{"historical":false}\n', encoding="utf-8")
    with pytest.raises(DestinationVerificationError):
        store.verify_chain()
    with pytest.raises(ValueError, match="LEGACY_ANCHOR_MISMATCH"):
        JsonlAuditStore.chained_successor(legacy)


def test_approved_legacy_audit_recovery_preserves_prior_successor(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "research.jsonl"
    legacy.write_text('{"historical":true}\n', encoding="utf-8")
    primary = JsonlAuditStore.chained_successor(legacy)
    primary.append(AuditEvent("RESEARCH_COMPLETED", NOW, {"safe": True}))
    primary_bytes = primary.path.read_bytes()
    legacy.write_text('{"historical":false}\n', encoding="utf-8")

    recovered = JsonlAuditStore.recover_chained_successor(legacy)

    assert primary.path.read_bytes() == primary_bytes
    assert recovered.path != primary.path
    assert recovered.verify_chain()
    receipt = json.loads(
        (tmp_path / "research.audit-recovery.json").read_text(encoding="utf-8")
    )
    assert receipt["primary_successor_sha256"]
    assert receipt["execution_allowed"] is False
    assert JsonlAuditStore.chained_successor(legacy).path == recovered.path


def test_chained_successor_rejects_modified_or_reordered_records(
    tmp_path: Path,
) -> None:
    store = JsonlAuditStore.chained_successor(tmp_path / "absent.jsonl")
    store.append(AuditEvent("FIRST_EVENT", NOW, {"number": 1}))
    store.append(AuditEvent("SECOND_EVENT", NOW, {"number": 2}))
    lines = store.path.read_text().splitlines()
    store.path.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n")
    with pytest.raises(DestinationVerificationError):
        store.verify_chain()


def test_secret_redactor_handles_nested_sensitive_fields() -> None:
    redacted = SecretRedactor().redact(
        {
            "api_key": "secret-value",
            "nested": {
                "Authorization": "Bearer value",
                "safe": "visible",
            },
            "items": [{"private-key": "hidden"}],
        }
    )
    assert redacted == {
        "api_key": "[REDACTED]",
        "nested": {
            "Authorization": "[REDACTED]",
            "safe": "visible",
        },
        "items": [{"private-key": "[REDACTED]"}],
    }


def test_secret_redactor_preserves_usage_counts_but_not_credentials() -> None:
    redacted = SecretRedactor().redact(
        {
            "input_tokens": 100,
            "cached_input_tokens": 25,
            "output_tokens": 20,
            "reasoning_tokens": 5,
            "total_tokens": 120,
            "token_accounting_source": "EXACT_PROVIDER",
            "access_token": "must-not-appear",
            "token": "must-not-appear-either",
            "token_count_guess": "still-sensitive-by-default",
        }
    )

    assert redacted == {
        "input_tokens": 100,
        "cached_input_tokens": 25,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "total_tokens": 120,
        "token_accounting_source": "EXACT_PROVIDER",
        "access_token": SecretRedactor.REDACTED,
        "token": SecretRedactor.REDACTED,
        "token_count_guess": SecretRedactor.REDACTED,
    }


def test_jsonl_store_appends_deterministic_redacted_event(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    store = JsonlAuditStore(path)
    event = AuditEvent(
        event_type="MARKET_SNAPSHOT_CREATED",
        timestamp=NOW,
        snapshot_id="snapshot-1",
        payload={"symbol": "HOTUSDT", "api_secret": "must-not-appear"},
    )
    store.append(event)
    store.append(event)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == lines[1]
    payload = json.loads(lines[0])
    assert payload["payload"]["api_secret"] == SecretRedactor.REDACTED
    assert "must-not-appear" not in lines[0]


def test_jsonl_store_verified_append_reads_destination_back(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    result = JsonlAuditStore(path).append_verified(
        AuditEvent(
            event_type="MARKET_SNAPSHOT_CREATED",
            timestamp=NOW,
            snapshot_id="snapshot-1",
            payload={"symbol": "HOTUSDT"},
        )
    )
    assert result.subject_id == "snapshot-1"
    assert json.loads(path.read_text(encoding="utf-8"))["snapshot_id"] == "snapshot-1"
    assert path.with_suffix(".jsonl.lock").exists()


def test_jsonl_store_idempotent_append_rejects_identity_drift(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit" / "idempotent-events.jsonl"
    store = JsonlAuditStore(path, durable=True, tamper_evident=True)
    event = AuditEvent(
        event_type="VIRTUAL_WALLET_RESET",
        timestamp=NOW,
        snapshot_id="reset-source:abc",
        payload={"reset_id": "reset:1", "capital": "1000"},
    )

    assert store.append_verified_idempotent(event) is not None
    assert store.append_verified_idempotent(event) is None
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    with pytest.raises(ValueError, match="JSONL_AUDIT_IDEMPOTENCY_CONFLICT"):
        store.append_verified_idempotent(
            AuditEvent(
                event_type=event.event_type,
                timestamp=event.timestamp,
                snapshot_id=event.snapshot_id,
                payload={"reset_id": "reset:2", "capital": "500"},
            )
        )


def test_jsonl_store_tamper_evident_chain_is_verified_and_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    fsync_calls: list[int] = []
    monkeypatch.setattr("ai4binance.storage.jsonl.os.fsync", fsync_calls.append)
    store = JsonlAuditStore(path, tamper_evident=True)

    first = store.append_verified(
        AuditEvent(
            event_type="MARKET_SNAPSHOT_CREATED",
            timestamp=NOW,
            snapshot_id="snapshot-1",
            payload={"symbol": "HOTUSDT"},
        )
    )
    second = store.append_verified(
        AuditEvent(
            event_type="MARKET_SNAPSHOT_CREATED",
            timestamp=NOW,
            snapshot_id="snapshot-2",
            payload={"symbol": "BTCUSDT"},
        )
    )

    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["tamper_evident"] is True
    assert records[0]["previous_record_sha256"] == "GENESIS"
    assert records[0]["chain_position"] == 1
    assert records[1]["previous_record_sha256"] == records[0]["record_sha256"]
    assert records[1]["chain_position"] == 2
    assert store.verify_chain() == records[1]["record_sha256"]
    assert first.subject_id == "snapshot-1"
    assert second.subject_id == "snapshot-2"
    assert len(fsync_calls) == 2


def test_jsonl_store_tamper_evident_chain_fails_closed_on_tampering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    store = JsonlAuditStore(path, tamper_evident=True)
    store.append_verified(
        AuditEvent(
            event_type="MARKET_SNAPSHOT_CREATED",
            timestamp=NOW,
            snapshot_id="snapshot-1",
            payload={"symbol": "HOTUSDT"},
        )
    )

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["payload"]["symbol"] = "TAMPERED"
    path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(
        DestinationVerificationError,
        match="JSONL_AUDIT_TAMPER_EVIDENT_CHAIN_INVALID",
    ):
        store.verify_chain()


def test_jsonl_store_verified_append_stops_on_failed_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    monkeypatch.setattr(
        JsonlAuditStore,
        "_last_event_unlocked",
        lambda self: {"snapshot_id": "tampered"},
    )
    with pytest.raises(DestinationVerificationError, match="JSONL_AUDIT"):
        JsonlAuditStore(path).append_verified(
            AuditEvent(
                event_type="MARKET_SNAPSHOT_CREATED",
                timestamp=NOW,
                snapshot_id="snapshot-1",
                payload={"symbol": "HOTUSDT"},
            )
        )


def test_jsonl_store_verified_append_uses_bounded_tail_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"event_type":"OLD_EVENT"}\n' * 10_000, encoding="utf-8")

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: pytest.fail("whole-file read is forbidden"),
    )
    result = JsonlAuditStore(path).append_verified(
        AuditEvent(
            event_type="MARKET_SNAPSHOT_CREATED",
            timestamp=NOW,
            snapshot_id="snapshot-tail",
            payload={"symbol": "HOTUSDT"},
        )
    )

    assert result.subject_id == "snapshot-tail"
    assert result.operation == "jsonl_append"


def test_jsonl_store_tail_read_handles_blank_lines_and_size_limit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"status":"ok"}\n\n \t\r\n')
    assert JsonlAuditStore(path)._last_event() == {"status": "ok"}

    path.write_bytes(b'{"payload":"' + (b"x" * 512) + b'"}\n')
    with pytest.raises(DestinationVerificationError, match="JSONL_AUDIT"):
        JsonlAuditStore(path, max_event_bytes=128)._last_event()


def test_jsonl_store_rejects_oversized_event_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "oversized.jsonl"
    event = AuditEvent(
        event_type="OVERSIZED_EVENT",
        timestamp=NOW,
        payload={"value": "x" * 512},
    )

    with pytest.raises(OSError, match="exceeds bounded write limit"):
        JsonlAuditStore(path, max_event_bytes=128).append_verified(event)

    assert not path.exists()


def test_bounded_jsonl_tail_returns_only_recent_nonempty_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(
        b'{"sequence":0}\n' * 10_000 + b'\n{"sequence":1}\n{"sequence":2}\n\n'
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: pytest.fail("whole-file read is forbidden"),
    )

    lines = read_bounded_jsonl_tail(path, max_lines=2)

    assert tuple(json.loads(line) for line in lines) == (
        {"sequence": 1},
        {"sequence": 2},
    )


def test_bounded_jsonl_tail_discards_partial_leading_record(tmp_path: Path) -> None:
    path = tmp_path / "large-records.jsonl"
    large = json.dumps({"id": 1, "value": "x" * 200_000}).encode()
    latest = json.dumps({"id": 2}).encode()
    path.write_bytes(b'{"id":0}\n' + large + b"\n" + latest + b"\n")

    assert read_bounded_jsonl_tail(path, max_lines=2, max_bytes=500_000) == (
        large,
        latest,
    )


def test_verified_write_result_rejects_inconsistent_states() -> None:
    with pytest.raises(ValueError, match="identity"):
        VerifiedWriteResult("", "event", VerificationStatus.VERIFIED)
    with pytest.raises(ValueError, match="cannot contain blockers"):
        VerifiedWriteResult(
            "audit.jsonl",
            "event",
            VerificationStatus.VERIFIED,
            ("BLOCKER",),
        )
    with pytest.raises(ValueError, match="requires blockers"):
        VerifiedWriteResult("audit.jsonl", "event", VerificationStatus.FAILED)


def test_read_json_object_verifies_object_payload(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"status":"ok"}', encoding="utf-8")

    assert read_json_object(path, blocker="STATE_VERIFY_FAILED")["status"] == "ok"

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(DestinationVerificationError, match="STATE_VERIFY_FAILED"):
        read_json_object(path, blocker="STATE_VERIFY_FAILED")

    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(DestinationVerificationError, match="STATE_VERIFY_FAILED"):
        read_json_object(path, blocker="STATE_VERIFY_FAILED")


def test_write_json_object_verified_reads_destination_back(tmp_path: Path) -> None:
    path = tmp_path / "state" / "latest.json"

    result = write_json_object_verified(
        path,
        {"status": "ok", "execution_allowed": False},
        blocker="STATE_VERIFY_FAILED",
        subject_id="state-1",
        indent=2,
    )

    assert result.subject_id == "state-1"
    assert result.operation == "json_state_write"
    assert result.expected_sha256 == result.observed_sha256
    assert result.verified_at is not None
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "ok"


def test_write_json_object_verified_compares_canonical_json_shapes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "latest.json"

    result = write_json_object_verified(
        path,
        {"blockers": ("FIRST", "SECOND")},
        blocker="STATE_VERIFY_FAILED",
    )

    assert result.expected_sha256 == result.observed_sha256
    assert json.loads(path.read_text(encoding="utf-8"))["blockers"] == [
        "FIRST",
        "SECOND",
    ]


def test_write_json_object_verified_stops_on_failed_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "latest.json"
    original = Path.read_text

    def tampered_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        payload = original(self, encoding, errors)
        return payload.replace('"ok"', '"tampered"') if self == path else payload

    monkeypatch.setattr(Path, "read_text", tampered_read_text)
    with pytest.raises(DestinationVerificationError, match="STATE_VERIFY_FAILED"):
        write_json_object_verified(
            path,
            {"status": "ok"},
            blocker="STATE_VERIFY_FAILED",
            subject_id="state-1",
        )


def test_write_json_object_verified_retries_transient_replace_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "latest.json"
    original_replace = destination_verification.os.replace
    attempts = 0
    delays: list[float] = []

    def flaky_replace(source: Path, destination: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "transient sharing violation")
        original_replace(source, destination)

    monkeypatch.setattr(destination_verification.os, "replace", flaky_replace)
    monkeypatch.setattr(destination_verification.time, "sleep", delays.append)

    result = write_json_object_verified(
        path,
        {"status": "ok"},
        blocker="STATE_VERIFY_FAILED",
    )

    assert result.status is VerificationStatus.VERIFIED
    assert attempts == 3
    assert delays == [0.01, 0.02]


def test_write_json_object_verified_preserves_persistent_replace_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "latest.json"
    attempts = 0

    def denied_replace(_source: Path, _destination: Path) -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError(5, "persistent sharing violation")

    monkeypatch.setattr(destination_verification.os, "replace", denied_replace)
    monkeypatch.setattr(destination_verification.time, "sleep", lambda _delay: None)

    with pytest.raises(PermissionError, match="persistent sharing violation"):
        write_json_object_verified(
            path,
            {"status": "ok"},
            blocker="STATE_VERIFY_FAILED",
        )

    assert attempts == 8


def test_jsonl_store_optional_durable_flush(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptors: list[int] = []
    monkeypatch.setattr("ai4binance.storage.jsonl.os.fsync", descriptors.append)
    JsonlAuditStore(tmp_path / "events.jsonl", durable=True).append(
        AuditEvent("TEST_EVENT", NOW, {"ok": True})
    )
    assert len(descriptors) == 1


@pytest.mark.parametrize("event_type", ["", "lowercase", "HAS SPACE"])
def test_audit_event_rejects_invalid_type(event_type: str) -> None:
    with pytest.raises(ValueError, match="uppercase snake case"):
        AuditEvent(event_type, NOW, {})


def test_audit_event_requires_aware_timestamp_and_nonblank_snapshot() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AuditEvent("TEST_EVENT", datetime(2026, 1, 1), {})
    with pytest.raises(ValueError, match="cannot be blank"):
        AuditEvent("TEST_EVENT", NOW, {}, snapshot_id=" ")


def test_verified_write_result_requires_operation() -> None:
    with pytest.raises(ValueError, match="operation is required"):
        VerifiedWriteResult(
            "audit.jsonl", "event", VerificationStatus.VERIFIED, operation=" "
        )


def test_jsonl_store_enforces_positive_bound_and_durable_chain(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        JsonlAuditStore(tmp_path / "events.jsonl", max_event_bytes=0)

    store = JsonlAuditStore(tmp_path / "chain.jsonl", tamper_evident=True)
    assert store.durable is True


def test_secret_redactor_handles_unordered_collections_and_scalars() -> None:
    redactor = SecretRedactor()
    assert redactor.redact(({"password": "hidden"}, "visible")) == [
        {"password": SecretRedactor.REDACTED},
        "visible",
    ]
    assert redactor.redact("visible") == "visible"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("tamper_evident"),
        lambda payload: payload.__setitem__("chain_position", 2),
        lambda payload: payload.__setitem__("previous_record_sha256", "broken"),
        lambda payload: payload.__setitem__("event_sha256", "0" * 64),
        lambda payload: payload.__setitem__("record_sha256", "0" * 64),
    ],
    ids=("unsealed", "position", "previous", "event-hash", "record-hash"),
)
def test_tamper_evident_chain_rejects_each_binding_drift(
    tmp_path: Path,
    mutator: object,
) -> None:
    path = tmp_path / "chain.jsonl"
    store = JsonlAuditStore(path, tamper_evident=True)
    store.append_verified(AuditEvent("TEST_EVENT", NOW, {"value": 1}))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutator)
    mutator(payload)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tamper-evident JSONL line"):
        store._verify_chain_state_unlocked()


@pytest.mark.parametrize("raw", [b"\n", b"[]\n", b"not-json\n"])
def test_tamper_evident_chain_rejects_malformed_lines(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "chain.jsonl"
    path.write_bytes(raw)

    with pytest.raises((ValueError, json.JSONDecodeError)):
        JsonlAuditStore(path, tamper_evident=True)._verify_chain_state_unlocked()


def test_bounded_jsonl_tail_rejects_invalid_limits_and_oversized_tail(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"value":"' + b"x" * 100 + b'"}\n')

    with pytest.raises(ValueError, match="limits must be positive"):
        read_bounded_jsonl_tail(path, max_lines=0)
    with pytest.raises(OSError, match="exceeds bounded read limit"):
        read_bounded_jsonl_tail(path, max_bytes=10)


class _PrimitiveEnum(Enum):
    VALUE = "value"


def test_to_primitive_covers_supported_values_and_rejects_objects() -> None:
    event = AuditEvent("TEST_EVENT", NOW, {"value": Decimal("1.5")})

    event_payload = cast(dict[str, object], safe_json.to_primitive(event))
    assert event_payload["event_type"] == "TEST_EVENT"
    assert safe_json.to_primitive(_PrimitiveEnum.VALUE) == "value"
    assert safe_json.to_primitive(NOW) == NOW.isoformat()
    assert safe_json.to_primitive(date(2026, 1, 1)) == "2026-01-01"
    assert safe_json.to_primitive(Decimal("1.5")) == "1.5"
    assert safe_json.to_primitive({"values": {2, 1}}) == {"values": [1, 2]}
    assert safe_json.to_primitive(("a", "b")) == ["a", "b"]
    assert safe_json.to_primitive(None) is None
    with pytest.raises(TypeError, match="not JSON serializable"):
        safe_json.to_primitive(object())

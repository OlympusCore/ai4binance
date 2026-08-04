"""Append-only audit storage and secret redaction tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def test_jsonl_store_verified_append_stops_on_failed_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    monkeypatch.setattr(
        JsonlAuditStore,
        "_last_event",
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

"""TEST_ONLY authorization-shaped values exercise validators, never real writes."""

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest

from ai4binance.governance import git_write_contract as contract

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
HASH = "a" * 64


@pytest.fixture(autouse=True)
def _test_only_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        contract,
        "datetime",
        SimpleNamespace(fromisoformat=datetime.fromisoformat, now=lambda _zone: NOW),
    )


def _challenge(
    operation: str = "COMMIT", channel: str = "NONINTERACTIVE"
) -> dict[str, Any]:
    subject: dict[str, Any] = {
        "repository_root_sha256": HASH,
        "git_common_directory_sha256": HASH,
        "head": "b" * 40,
        "branch": "refs/heads/main",
        "hooks_path": "scripts/git-hooks",
        "author_identity_sha256": HASH,
        "committer_identity_sha256": HASH,
        "placeholder_identity": False,
        "staged_tree": "c" * 40,
        "remote_name": "",
        "remote_url_sha256": "",
        "push_updates": [],
    }
    if operation == "PUSH":
        subject.update(
            staged_tree="",
            remote_name="origin",
            remote_url_sha256=HASH,
            push_updates=[
                {
                    "local_ref": "refs/heads/main",
                    "local_oid": "b" * 40,
                    "remote_ref": "refs/heads/main",
                    "remote_oid": "c" * 40,
                }
            ],
        )
    return {
        "schema_version": 1,
        "status": "PENDING",
        "operation": operation,
        "channel": channel,
        "nonce": "d" * 64,
        "created_at_utc": NOW.isoformat(),
        "expires_at_utc": (NOW + timedelta(minutes=5)).isoformat(),
        "subject": subject,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _approval(challenge: dict[str, Any]) -> dict[str, Any]:
    # This is an in-memory test fixture. No approval helper or real Git is invoked.
    return {
        "schema_version": 1,
        "status": "APPROVED",
        "operation": challenge["operation"],
        "challenge_sha256": HASH,
        "approval_text_sha256": HASH,
        "approved_at_utc": NOW.isoformat(),
        "expires_at_utc": challenge["expires_at_utc"],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


@pytest.mark.parametrize("operation", ["COMMIT", "PUSH"])
@pytest.mark.parametrize("channel", ["NONINTERACTIVE", "INTERACTIVE"])
def test_exact_operation_subject_and_channel_are_validated_without_granting_authority(
    operation: str,
    channel: str,
) -> None:
    challenge = _challenge(operation, channel)
    before = copy.deepcopy(challenge)
    contract.validate_challenge(challenge)
    contract.validate_approval(_approval(challenge), challenge, HASH, NOW)
    contract.validate_consume_context(
        {
            "challenge": challenge,
            "requested_operation": operation.lower(),
            "channel": channel.lower(),
            "approval_text": operation.lower(),
        }
    )
    contract.evaluate({"operation": "shape", "challenge": challenge})
    contract.evaluate({"operation": "fresh", "challenge": challenge})
    contract.evaluate(
        {
            "operation": "subject",
            "challenge": challenge,
            "current": challenge["subject"],
        }
    )
    contract.evaluate(
        {
            "operation": "approval",
            "challenge": challenge,
            "approval": _approval(challenge),
            "challenge_hash": HASH,
        }
    )
    assert challenge == before
    assert challenge["status"] == "PENDING"
    assert challenge["execution_allowed"] is False


@pytest.mark.parametrize("minutes", [0, -1, 5.001, 30])
def test_challenge_lifetime_cannot_be_empty_negative_or_extended(
    minutes: float,
) -> None:
    challenge = _challenge()
    challenge["expires_at_utc"] = (NOW + timedelta(minutes=minutes)).isoformat()
    with pytest.raises(ValueError, match="GIT_WRITE_AUTHORIZATION_EXPIRY_INVALID"):
        contract.validate_challenge(challenge)


@pytest.mark.parametrize("field", ["created_at_utc", "expires_at_utc"])
def test_timezone_is_required_on_both_challenge_timestamps(field: str) -> None:
    challenge = _challenge()
    challenge[field] = NOW.replace(tzinfo=None).isoformat()
    with pytest.raises(ValueError, match="GIT_WRITE_AUTHORIZATION_TIMESTAMP_INVALID"):
        contract.validate_challenge(challenge)


def test_interactive_placeholder_identity_is_rejected() -> None:
    challenge = _challenge(channel="INTERACTIVE")
    challenge["subject"]["placeholder_identity"] = True
    with pytest.raises(ValueError, match="PLACEHOLDER_IDENTITY_BLOCKED"):
        contract.validate_challenge(challenge)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("staged_tree", "not-a-tree"),
        ("remote_name", "origin"),
        ("remote_url_sha256", HASH),
        ("push_updates", _challenge("PUSH")["subject"]["push_updates"]),
    ],
)
def test_commit_subject_rejects_remote_updates_and_invalid_tree(
    field: str, value: object
) -> None:
    challenge = _challenge()
    challenge["subject"][field] = value
    with pytest.raises(ValueError, match="COMMIT_SUBJECT_INVALID"):
        contract.validate_challenge(challenge)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("staged_tree", "b" * 40),
        ("remote_name", "  "),
        ("remote_url_sha256", "bad-digest"),
        ("push_updates", []),
    ],
)
def test_push_subject_requires_exact_remote_and_nonempty_updates(
    field: str, value: object
) -> None:
    challenge = _challenge("PUSH")
    challenge["subject"][field] = value
    with pytest.raises(ValueError, match="PUSH_SUBJECT_INVALID"):
        contract.validate_challenge(challenge)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "PUSH"),
        ("challenge_sha256", "e" * 64),
        ("expires_at_utc", (NOW + timedelta(minutes=4)).isoformat()),
    ],
)
def test_receipt_cannot_be_reused_for_changed_operation_subject_or_expiry(
    field: str, value: object
) -> None:
    challenge = _challenge()
    approval = _approval(challenge)
    approval[field] = value
    with pytest.raises(ValueError, match="GIT_WRITE_AUTHORIZATION_APPROVAL_INVALID"):
        contract.validate_approval(approval, challenge, HASH, NOW)


@pytest.mark.parametrize("seconds", [-1, 61, 301])
def test_receipt_time_must_be_within_challenge_and_current_clock(seconds: int) -> None:
    challenge = _challenge()
    approval = _approval(challenge)
    approval["approved_at_utc"] = (NOW + timedelta(seconds=seconds)).isoformat()
    with pytest.raises(ValueError, match="APPROVAL_TIME_INVALID"):
        contract.validate_approval(approval, challenge, HASH, NOW)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("requested_operation", "PUSH", "OPERATION_MISMATCH"),
        ("channel", "INTERACTIVE", "CHANNEL_MISMATCH"),
    ],
)
def test_consume_context_cannot_change_the_approved_boundary(
    field: str, value: str, error: str
) -> None:
    request = {
        "challenge": _challenge(),
        "requested_operation": "COMMIT",
        "channel": "NONINTERACTIVE",
        "approval_text": "",
    }
    request[field] = value
    with pytest.raises(ValueError, match=error):
        contract.evaluate({**request, "operation": "consume_context"})


def test_interactive_context_requires_the_actual_operation_response() -> None:
    request = {
        "challenge": _challenge(channel="INTERACTIVE"),
        "requested_operation": "",
        "channel": "INTERACTIVE",
        "approval_text": "yes",
    }
    with pytest.raises(ValueError, match="INTERACTIVE_APPROVAL_DECLINED"):
        contract.validate_consume_context(request)
    with pytest.raises(ValueError, match="CHANNEL_MISMATCH"):
        contract.validate_approval_text(request)


@pytest.mark.parametrize(
    "response",
    [
        "",
        "COMMIT",
        "yes",
        f"APPROVE_AI4BINANCE_GIT_PUSH {HASH}",
        f"APPROVE_AI4BINANCE_GIT_COMMIT {'e' * 64}",
    ],
)
def test_noninteractive_response_must_be_exact_and_operation_specific(
    response: str,
) -> None:
    request = {
        "challenge": _challenge(),
        "challenge_hash": HASH,
        "approval_text": response,
    }
    with pytest.raises(ValueError, match="EXACT_APPROVAL_REQUIRED"):
        contract.evaluate({**request, "operation": "approve_text"})


def test_exact_text_is_validation_only_and_expired_or_changed_subject_still_fails() -> (
    None
):
    challenge = _challenge()
    contract.evaluate(
        {
            "operation": "approve_text",
            "challenge": challenge,
            "challenge_hash": HASH,
            "approval_text": f"APPROVE_AI4BINANCE_GIT_COMMIT {HASH}",
        }
    )
    challenge.update(
        created_at_utc=(NOW - timedelta(minutes=6)).isoformat(),
        expires_at_utc=(NOW - timedelta(minutes=1)).isoformat(),
    )
    with pytest.raises(ValueError, match="AUTHORIZATION_EXPIRED"):
        contract.evaluate({"operation": "fresh", "challenge": challenge})
    with pytest.raises(ValueError, match="SUBJECT_MISMATCH"):
        contract.evaluate(
            {"operation": "subject", "challenge": _challenge(), "current": {}}
        )
    with pytest.raises(ValueError, match="OPERATION_INVALID"):
        contract.evaluate({"operation": "unknown", "challenge": _challenge()})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"{}", "GIT_WRITE_AUTHORIZATION_REQUEST_INVALID"),
        (b"\xff", "GIT_WRITE_AUTHORIZATION_REQUEST_INVALID"),
        (b"x" * 262145, "GIT_WRITE_AUTHORIZATION_REQUEST_TOO_LARGE"),
        (
            json.dumps(
                {
                    "operation": "shape",
                    "challenge": {"sensitive_test_value": "do-not-echo"},
                }
            ).encode(),
            "GIT_WRITE_AUTHORIZATION_CHALLENGE_INVALID",
        ),
    ],
    ids=["invalid-json", "invalid-utf8", "oversized-request", "invalid-shape"],
)
def test_cli_errors_are_bounded_and_never_echo_request_contents(
    raw: bytes,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=BytesIO(raw)))
    assert contract.main() == 2
    assert capsys.readouterr().out == expected + "\n"


def test_cli_valid_request_returns_no_authorization_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.dumps({"operation": "shape", "challenge": _challenge()}).encode()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=BytesIO(raw)))
    assert contract.main() == 0
    assert capsys.readouterr().out == "VALID\n"

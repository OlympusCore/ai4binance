"""Validate Git authorization artifacts; never grant or consume authorization."""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]


def _timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("GIT_WRITE_AUTHORIZATION_TIMESTAMP_INVALID")
    return result


def _shape(value: object, kind: str) -> None:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (root / "schemas/governance/git_write_authorization.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema["$defs"][kind])
    if not validator.is_valid(value):
        raise ValueError(f"GIT_WRITE_AUTHORIZATION_{kind.upper()}_INVALID")


def validate_challenge(challenge: dict[str, Any]) -> None:
    """Preserve exact shape, bounded lifetime and operation-specific subjects."""
    _shape(challenge, "challenge")
    created = _timestamp(challenge["created_at_utc"])
    expires = _timestamp(challenge["expires_at_utc"])
    if not timedelta(0) < expires - created <= timedelta(minutes=5):
        raise ValueError("GIT_WRITE_AUTHORIZATION_EXPIRY_INVALID")
    subject = challenge["subject"]
    if challenge["channel"] == "INTERACTIVE" and subject["placeholder_identity"]:
        raise ValueError("GIT_WRITE_AUTHORIZATION_PLACEHOLDER_IDENTITY_BLOCKED")
    if challenge["operation"] == "COMMIT":
        if (
            not re.fullmatch(r"[0-9a-f]{40,64}", subject["staged_tree"])
            or subject["remote_name"]
            or subject["remote_url_sha256"]
            or subject["push_updates"]
        ):
            raise ValueError("GIT_WRITE_AUTHORIZATION_COMMIT_SUBJECT_INVALID")
    elif (
        subject["staged_tree"]
        or not subject["remote_name"].strip()
        or not re.fullmatch(r"[0-9a-f]{64}", subject["remote_url_sha256"])
        or not subject["push_updates"]
    ):
        raise ValueError("GIT_WRITE_AUTHORIZATION_PUSH_SUBJECT_INVALID")


def validate_approval(
    approval: dict[str, Any],
    challenge: dict[str, Any],
    challenge_hash: str,
    now: datetime,
) -> None:
    """Bind the existing human approval receipt to the exact challenge."""
    _shape(approval, "approval")
    validate_challenge(challenge)
    if (
        approval["operation"] != challenge["operation"]
        or approval["challenge_sha256"] != challenge_hash
        or approval["expires_at_utc"] != challenge["expires_at_utc"]
    ):
        raise ValueError("GIT_WRITE_AUTHORIZATION_APPROVAL_INVALID")
    approved = _timestamp(approval["approved_at_utc"])
    if not _timestamp(challenge["created_at_utc"]) <= approved <= _timestamp(
        approval["expires_at_utc"]
    ) or approved > now + timedelta(minutes=1):
        raise ValueError("GIT_WRITE_AUTHORIZATION_APPROVAL_TIME_INVALID")


def validate_consume_context(request: dict[str, Any]) -> None:
    challenge = request["challenge"]
    if request["requested_operation"] and (
        request["requested_operation"].upper() != challenge["operation"]
    ):
        raise ValueError("GIT_WRITE_AUTHORIZATION_OPERATION_MISMATCH")
    if request["channel"].upper() != challenge["channel"]:
        raise ValueError("GIT_WRITE_AUTHORIZATION_CHANNEL_MISMATCH")
    if challenge["channel"] == "INTERACTIVE" and (
        request["approval_text"].upper() != challenge["operation"]
    ):
        raise ValueError("GIT_WRITE_AUTHORIZATION_INTERACTIVE_APPROVAL_DECLINED")


def validate_approval_text(request: dict[str, Any]) -> None:
    challenge = request["challenge"]
    if challenge["channel"] != "NONINTERACTIVE":
        raise ValueError("GIT_WRITE_AUTHORIZATION_CHANNEL_MISMATCH")
    expected = (
        f"APPROVE_AI4BINANCE_GIT_{challenge['operation']} {request['challenge_hash']}"
    )
    if request["approval_text"] != expected:
        raise ValueError("GIT_WRITE_AUTHORIZATION_EXACT_APPROVAL_REQUIRED")


def evaluate(request: dict[str, Any]) -> None:
    """Validate one boundary request without filesystem or Git mutation."""
    operation = request["operation"]
    challenge = request["challenge"]
    validate_challenge(challenge)
    now = datetime.now(UTC)
    if operation == "shape":
        return
    if operation == "fresh":
        if _timestamp(challenge["expires_at_utc"]) <= now:
            raise ValueError("GIT_WRITE_AUTHORIZATION_EXPIRED")
    elif operation == "subject":
        if challenge["subject"] != request["current"]:
            raise ValueError("GIT_WRITE_AUTHORIZATION_SUBJECT_MISMATCH")
    elif operation == "approval":
        validate_approval(
            request["approval"], challenge, request["challenge_hash"], now
        )
    elif operation == "approve_text":
        validate_approval_text(request)
    elif operation == "consume_context":
        validate_consume_context(request)
    else:
        raise ValueError("GIT_WRITE_AUTHORIZATION_OPERATION_INVALID")


def main() -> int:
    """Emit only a deterministic error code, never authorization contents."""
    try:
        raw = sys.stdin.buffer.read(262_145)
        if len(raw) > 262_144:
            raise ValueError("GIT_WRITE_AUTHORIZATION_REQUEST_TOO_LARGE")
        evaluate(json.loads(raw.decode("utf-8-sig")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc)
        print(
            code
            if re.fullmatch(r"GIT_WRITE_AUTHORIZATION_[A-Z_]+", code)
            else "GIT_WRITE_AUTHORIZATION_REQUEST_INVALID"
        )
        return 2
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

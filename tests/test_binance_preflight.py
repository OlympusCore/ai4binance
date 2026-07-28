"""Secret-safe Binance preflight diagnostics tests."""

from __future__ import annotations

from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from ai4binance.ops import binance_preflight
from ai4binance.ops.binance_preflight import build_preflight_report


class ResponseStub:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> ResponseStub:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int) -> bytes:
        del limit
        return self.payload


def test_binance_preflight_reports_ready_without_sensitive_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=public-key\nBINANCE_API_SECRET=private-secret\n",
        encoding="utf-8",
    )
    payloads = iter(
        (
            b'{"serverTime":1700000000000}',
            b'{"serverTime":1700000000100}',
            b'{"canTrade":true,"balances":[{"asset":"HOT","free":"1"}]}',
            b'{"totalWalletBalance":"123"}',
        )
    )

    def opener(_request: Request, *, timeout: float) -> ResponseStub:
        assert timeout == 10.0
        return ResponseStub(next(payloads))

    report = build_preflight_report(
        clock_ms=lambda: 1_700_000_000_000,
        opener=opener,
    )

    assert report["status"] == "READY"
    assert report["blockers"] == ()
    text = str(report)
    assert "private-secret" not in text
    assert "balances" not in text
    assert "totalWalletBalance" not in text


def test_binance_preflight_redacts_http_error_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=public-key\nBINANCE_API_SECRET=private-secret\n",
        encoding="utf-8",
    )

    def opener(request: Request, *, timeout: float) -> ResponseStub:
        assert timeout == 10.0
        if "/api/v3/account" in request.full_url:
            raise HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                Message(),
                BytesIO(b'{"code":-2015,"msg":"Invalid API-key permissions."}'),
            )
        return ResponseStub(b'{"serverTime":1700000000000}')

    report = build_preflight_report(opener=opener)

    assert report["status"] == "DEGRADED"
    blockers = cast(tuple[str, ...], report["blockers"])
    assert "spot_account:HTTP_ERROR" in blockers
    endpoints = cast(tuple[dict[str, object], ...], report["endpoints"])
    endpoint = next(row for row in endpoints if row["name"] == "spot_account")
    assert endpoint["binance_code"] == -2015
    assert endpoint["binance_message"] == "Invalid API-key permissions."
    assert "private-secret" not in str(report)


def test_binance_preflight_blocks_missing_credentials(tmp_path: Path) -> None:
    report = build_preflight_report(credential_file=tmp_path / "missing.env")

    assert report["credential_status"] == "BLOCKED"
    assert report["execution_allowed"] is False
    assert report["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert report["blockers"]


def test_binance_preflight_reports_transport_and_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=public-key\nBINANCE_API_SECRET=private-secret\n",
        encoding="utf-8",
    )
    payloads = iter((TimeoutError("slow"), b"not-json", b"[]", b"{}"))

    def opener(_request: Request, *, timeout: float) -> ResponseStub:
        assert timeout == 10.0
        payload = next(payloads)
        if isinstance(payload, BaseException):
            raise payload
        return ResponseStub(payload)

    report = build_preflight_report(opener=opener)

    assert report["status"] == "DEGRADED"
    endpoints = cast(tuple[dict[str, object], ...], report["endpoints"])
    assert endpoints[0]["status"] == "TRANSPORT_ERROR"
    assert endpoints[1]["status"] == "INVALID_JSON"
    assert endpoints[2]["status"] == "UNEXPECTED_PAYLOAD"
    assert endpoints[3]["status"] == "EMPTY_ACCOUNT_PAYLOAD"


def test_binance_preflight_handles_malformed_binance_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=public-key\nBINANCE_API_SECRET=private-secret\n",
        encoding="utf-8",
    )

    def opener(request: Request, *, timeout: float) -> ResponseStub:
        assert timeout == 10.0
        raise HTTPError(
            request.full_url,
            418,
            "Teapot",
            Message(),
            BytesIO(b"not-json"),
        )

    report = build_preflight_report(opener=opener)

    endpoints = cast(tuple[dict[str, object], ...], report["endpoints"])
    assert endpoints[0]["binance_code"] is None
    assert endpoints[0]["binance_message"] == ""


def test_binance_preflight_main_returns_degraded_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        binance_preflight,
        "build_preflight_report",
        lambda: {
            "command": "binance-preflight",
            "status": "DEGRADED",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )

    assert binance_preflight.main() == 2
    assert '"status": "DEGRADED"' in capsys.readouterr().out

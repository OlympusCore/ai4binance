from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 5, 20, 30, tzinfo=UTC)


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is required for assistant context tests")
    return executable


def _account_payload(created_at: datetime = NOW) -> dict[str, object]:
    return {
        "created_at": created_at.isoformat(),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "spot": {"wallet_status": "READY"},
        "inventory": [
            {"asset": "BTC", "total": "0.01"},
            {"asset": "USDT", "total": "100"},
        ],
        "portfolio_analytics": {"total_value_usdt": "123.456"},
        "investment_management": {
            "recommendations": [
                {
                    "category": "NEW_OPPORTUNITY",
                    "action": "WATCHLIST",
                    "execution_allowed": False,
                },
                {
                    "category": "PORTFOLIO_RISK",
                    "action": "REDUCE_RISK_REVIEW",
                    "execution_allowed": False,
                },
            ]
        },
    }


def _invoke_helper(
    state_path: Path,
    *,
    input_text: str,
    context_text: str = "",
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "AI4B_TEST_STATE_PATH": str(state_path),
            "AI4B_TEST_INPUT": input_text,
            "AI4B_TEST_CONTEXT": context_text,
            "AI4B_TEST_NOW": NOW.isoformat(),
        }
    )
    helper = ROOT / "scripts" / "assistant_wallet_context.ps1"
    command = " ".join(
        [
            f". '{helper}' ;",
            "$result = Get-AI4BinanceWalletAnswer",
            "-InputText $env:AI4B_TEST_INPUT",
            "-ContextText $env:AI4B_TEST_CONTEXT",
            "-StatePath $env:AI4B_TEST_STATE_PATH",
            "-Now ([DateTimeOffset]$env:AI4B_TEST_NOW) ;",
            "$result | ConvertTo-Json -Compress",
        ]
    )
    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return cast(dict[str, Any], json.loads(completed.stdout))


def test_wallet_context_returns_verified_value_and_contents(tmp_path: Path) -> None:
    state_path = tmp_path / "account-management.json"
    state_path.write_text(json.dumps(_account_payload()), encoding="utf-8")

    value = _invoke_helper(state_path, input_text="binance_wallet su anki deger")
    contents = _invoke_helper(state_path, input_text="cüzdan ne içeriyor")

    assert value["handled"] is True
    assert value["evidence_status"] == "VERIFIED_LOCAL_SNAPSHOT"
    assert value["query_kind"] == "VALUE"
    assert "123.46 USDT" in value["message"]
    assert contents["query_kind"] == "CONTENTS"
    assert "BTC, USDT" in contents["message"]
    assert "0.01" not in contents["message"]


def test_wallet_context_corrects_alias_and_reports_research_only_opportunity(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "account-management.json"
    state_path.write_text(json.dumps(_account_payload()), encoding="utf-8")

    definition = _invoke_helper(
        state_path, input_text="binan_wallet sistemde tan\u0131ml\u0131 m\u0131"
    )
    opportunity = _invoke_helper(
        state_path, input_text="binance_wallet için f\u0131rsat var m\u0131"
    )

    assert definition["query_kind"] == "DEFINITION"
    assert "kanonik bir bilesen adi degil" in definition["message"]
    assert opportunity["query_kind"] == "OPPORTUNITY"
    assert "1 research-only izleme adayi" in opportunity["message"]
    assert "canli emir yetkisi kapali" in opportunity["message"]


def test_wallet_follow_up_uses_recent_context(tmp_path: Path) -> None:
    state_path = tmp_path / "account-management.json"
    state_path.write_text(json.dumps(_account_payload()), encoding="utf-8")

    result = _invoke_helper(
        state_path,
        input_text="şuan ki değer",
        context_text="binance_wallet sistemde tanimli mi",
    )

    assert result["handled"] is True
    assert result["query_kind"] == "VALUE"
    assert "123.46 USDT" in result["message"]


@pytest.mark.parametrize(
    "payload",
    [
        _account_payload(NOW - timedelta(seconds=181)),
        {**_account_payload(), "execution_allowed": True},
        {**_account_payload(), "BINANCE_API_SECRET": "forbidden"},
    ],
)
def test_wallet_context_fails_closed_for_untrusted_state(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    state_path = tmp_path / "account-management.json"
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _invoke_helper(state_path, input_text="cuzdan guncel durum")

    assert result["handled"] is True
    assert result["evidence_status"] == "DATA_UNAVAILABLE"
    assert "123.46" not in result["message"]


def test_non_wallet_query_is_not_intercepted(tmp_path: Path) -> None:
    result = _invoke_helper(tmp_path / "missing.json", input_text="nasilsin")

    assert result == {
        "handled": False,
        "evidence_status": "NOT_APPLICABLE",
        "query_kind": "NONE",
        "message": "",
    }


def test_timestamp_conversion_accepts_aware_datetime_and_rejects_naive() -> None:
    helper = ROOT / "scripts" / "assistant_wallet_context.ps1"
    command = " ".join(
        [
            f". '{helper}' ;",
            "$aware = [DateTime]::SpecifyKind(",
            "[DateTime]::Parse('2026-09-05T20:30:00'),",
            "[DateTimeKind]::Utc) ;",
            "$converted = ConvertTo-AI4BinanceDateTimeOffset -Value $aware ;",
            "$naiveRejected = $false ;",
            "try {",
            "$naive = [DateTime]::SpecifyKind($aware, [DateTimeKind]::Unspecified) ;",
            "[void](ConvertTo-AI4BinanceDateTimeOffset -Value $naive)",
            "} catch { $naiveRejected = $true } ;",
            "[pscustomobject]@{",
            "converted = $converted.ToString('o');",
            "naive_rejected = $naiveRejected",
            "} | ConvertTo-Json -Compress",
        ]
    )

    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)

    assert payload == {
        "converted": "2026-09-05T20:30:00.0000000+00:00",
        "naive_rejected": True,
    }


def test_assistant_answer_formatter_removes_role_markers_and_host_timestamp() -> None:
    helper = ROOT / "scripts" / "assistant_wallet_context.ps1"
    turkey_marker = "\U0001f1f9\U0001f1f7"
    environment = os.environ.copy()
    environment["AI4B_TEST_ANSWER"] = (
        f"Assistant: {turkey_marker}:\n:\nDogrulanmis cevap.\n"
        "[Europe/Istanbul time: 2026-09-05 23:20:25 +03:00]"
    )
    command = (
        f". '{helper}' ; Format-AI4BinanceAssistantAnswer -Answer $env:AI4B_TEST_ANSWER"
    )

    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.stdout.strip() == "Dogrulanmis cevap."

"""Accounting daemon resilience proof contracts."""

from __future__ import annotations

import json

import pytest

from ai4binance.cli import accounting as cli_accounting
from ai4binance.config import Settings
from ai4binance.exchange.errors import ExchangeTransportError


def test_accounting_rest_daemon_continues_after_expected_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(runtime_cycle_interval_seconds=5)
    outcomes = iter(("fail", "ok"))

    def collect_once(_settings: Settings) -> tuple[dict[str, object], int]:
        if next(outcomes) == "fail":
            raise ExchangeTransportError("private exchange request failed")
        return (
            {
                "command": "accounting-collect-once",
                "status": "COLLECTED",
                "blockers": (),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            0,
        )

    monkeypatch.setattr(cli_accounting, "accounting_collect_once", collect_once)
    monkeypatch.setattr("ai4binance.cli.accounting.time.sleep", lambda _seconds: None)

    assert cli_accounting.accounting_collect_daemon(settings, max_cycles=2) == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["status"] == "DEGRADED"
    assert lines[0]["blockers"] == ["ACCOUNTING_PROVIDER_CYCLE_FAILED"]
    assert lines[0]["error_type"] == "ExchangeTransportError"
    assert lines[0]["execution_allowed"] is False
    assert lines[0]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert lines[1]["status"] == "COLLECTED"


def test_accounting_rest_daemon_stops_after_bounded_provider_failure_budget(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(runtime_cycle_interval_seconds=5)

    def collect_once(_settings: Settings) -> tuple[dict[str, object], int]:
        raise ExchangeTransportError("private exchange request failed")

    monkeypatch.setattr(cli_accounting, "accounting_collect_once", collect_once)
    monkeypatch.setattr("ai4binance.cli.accounting.time.sleep", lambda _seconds: None)

    assert cli_accounting.accounting_collect_daemon(settings, max_cycles=None) == 2

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(lines) == 3
    assert lines[-1]["status"] == "CIRCUIT_OPEN"
    assert lines[-1]["consecutive_failures"] == 3
    assert lines[-1]["blockers"] == ["ACCOUNTING_PROVIDER_CIRCUIT_OPEN"]
    assert lines[-1]["execution_allowed"] is False
    assert lines[-1]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_accounting_rest_daemon_does_not_hide_unexpected_code_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(runtime_cycle_interval_seconds=5)

    def collect_once(_settings: Settings) -> tuple[dict[str, object], int]:
        raise TypeError("programmer error")

    monkeypatch.setattr(cli_accounting, "accounting_collect_once", collect_once)

    with pytest.raises(TypeError, match="programmer error"):
        cli_accounting.accounting_collect_daemon(settings, max_cycles=1)

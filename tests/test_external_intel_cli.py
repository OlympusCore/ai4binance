from __future__ import annotations

import json
from typing import cast

import pytest

from ai4binance.cli import main
from ai4binance.external_intel.__main__ import main as external_intel_main
from ai4binance.external_intel.cli.commands import (
    external_intel_payload,
    external_intel_universe_payload,
)


def test_external_intel_payload_is_report_only_and_degraded() -> None:
    payload = external_intel_payload(symbol="HOTUSDT")
    blockers = cast(tuple[str, ...], payload["blockers"])

    assert payload["status"] == "DEGRADED"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert "DATA_UNAVAILABLE" in blockers


def test_external_intel_universe_payload_exposes_exclusions() -> None:
    payload = external_intel_universe_payload()
    eligible_assets = cast(tuple[str, ...], payload["eligible_assets"])
    excluded_assets = cast(dict[str, object], payload["excluded_assets"])

    assert payload["execution_allowed"] is False
    assert "HOT" in eligible_assets
    assert "USDT" in excluded_assets


def test_external_intel_standalone_cli_reports_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert external_intel_main(["scan", "--symbol", "HOTUSDT"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "external-intel-scan"
    assert payload["decision_governance_impact"]["execution_allowed"] is False


def test_main_cli_external_intel_command_is_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["external-intel", "--symbol", "HOTUSDT"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "external-intel"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_main_cli_open_web_command_preserves_authority_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    safe_payload = {
        "command": "external-intel-open-web",
        "status": "READY",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    monkeypatch.setattr(
        "ai4binance.cli.open_web_payload", lambda **_kwargs: safe_payload
    )

    assert main(["external-intel-open-web", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload == safe_payload


def test_standalone_open_web_command_accepts_seed_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_payload(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "command": "external-intel-open-web",
            "status": "DEGRADED",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    monkeypatch.setattr(
        "ai4binance.external_intel.__main__.open_web_payload", fake_payload
    )
    seed = "https://github.blog/example/"

    assert external_intel_main(["open-web", "--seed-url", seed]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert captured["seed_urls"] == (seed,)
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

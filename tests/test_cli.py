"""CLI smoke tests."""

import importlib
import json
import os
import runpy
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import ai4binance.cli.runtime as runtime_cli
import ai4binance.cli.shared as cli_shared
import ai4binance.cli.status as status_cli
from ai4binance.application import WhaleFusionCycle
from ai4binance.cli import build_read_only_runtime, main
from ai4binance.cli.bootstrap import SnapshotAcquirer, parse_arguments
from ai4binance.cli.commands import (
    COMMAND_SPECS,
    available_command_names,
    canonical_command,
    command_catalog_payload,
)
from ai4binance.cli.dge import dge_replay_payload, dge_shadow_rules_payload
from ai4binance.cli.output import render_payload
from ai4binance.config import Settings
from ai4binance.enterprise import GpuResourceGovernor, GpuTelemetrySnapshot
from ai4binance.exchange.errors import ExchangeTransportError
from ai4binance.governance.replay import DgeReplayResult
from ai4binance.reporting import to_primitive
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle


def test_cli_module_preserves_package_shim_for_submodules() -> None:
    import ai4binance.cli as cli_module

    assert cli_module.__file__ is not None
    cli_file = Path(cli_module.__file__).resolve()
    assert cli_file.name == "cli.py"
    assert list(cli_module.__path__) == [str(cli_file.with_suffix(""))]

    accounting_module = importlib.import_module("ai4binance.cli.accounting")
    assert accounting_module.__file__ is not None
    assert Path(accounting_module.__file__).resolve() == (
        cli_file.with_suffix("") / "accounting.py"
    )
    assert cli_module.build_read_only_runtime is build_read_only_runtime


def test_cli_module_entrypoint_executes_main_for_python_dash_m(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["ai4binance.cli", "status"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("ai4binance.cli", run_name="__main__")

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_state"] == "NO_TRADE"
    assert payload["trading_mode"] == "paper"
    assert payload["execution_allowed"] is False
    assert payload["live_gate"]["status"] == "LIVE_ORDER_BLOCKED"


def test_status_is_complete_and_safe_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        GpuResourceGovernor,
        "collect_telemetry",
        lambda self: GpuTelemetrySnapshot.unavailable(source="unit-test"),
    )

    assert main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "NO_TRADE"
    assert payload["decision_state"] == "NO_TRADE"
    assert payload["setup_tier"] == "NO_TRADE"
    assert payload["validation_status"] == "UNVALIDATED"
    assert payload["execution_allowed"] is False
    assert payload["trading_mode"] == "paper"
    assert payload["order_mode"] == "manual"
    assert payload["timeframes"] == ["5m", "15m", "1h", "4h", "1d"]
    assert payload["live_gate"]["status"] == "LIVE_ORDER_BLOCKED"
    assert payload["virtual_market_gate"]["execution_surface"] == "VIRTUAL_MARKET"
    assert payload["virtual_market_gate"]["automation_mode"] == (
        "BOUNDED_AUTONOMOUS_SIMULATION"
    )
    assessment = cast(dict[str, object], payload["telemetry_assessment"])
    assert assessment["healthy"] is False
    assert assessment["source_label"] == "unit-test"
    assert assessment["blockers"] == ["CUDA_UNAVAILABLE"]
    assert "allow_auto_live_orders" in payload["live_gate"]["blockers"]
    assert "risk_penalty_score" in payload["sub_scores"]

    text = render_payload(payload, output_format="text", command="status")
    assert f"Status: {payload['symbol']}" in text
    assert "- telemetry_assessment: False unit-test ['CUDA_UNAVAILABLE']" in text
    assert "virtual_market_gate: BOUNDED_AUTONOMOUS_SIMULATION" in text
    assert "virtual_market_gate_authority_profile:" in text
    assert "virtual_market_gate_live: LIVE_ORDER_BLOCKED" in text


def test_status_and_virtual_runtime_share_virtual_market_gate_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared_payload = cast(
        dict[str, object], to_primitive(cli_shared.virtual_market_gate_payload())
    )

    assert main(["status"]) == 0
    status_payload = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert main(["virtual-market-once"]) == 0
    runtime_payload = cast(dict[str, object], json.loads(capsys.readouterr().out))

    shared_keys = (
        "execution_surface",
        "automation_mode",
        "authority_profile_id",
        "manual_confirmation_required",
        "virtual_simulation_allowed",
        "auto_simulation_allowed",
        "paper_execution_allowed",
        "external_order_allowed",
        "live_order_allowed",
        "bounded_simulation_only",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status",
        "blockers",
    )
    status_gate = cast(dict[str, object], status_payload["virtual_market_gate"])
    for key in shared_keys:
        assert status_gate[key] == shared_payload[key]
        assert runtime_payload[key] == shared_payload[key]


def test_confirm_live_sets_only_one_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status", "--confirm-live"]) == 0
    payload = cast(dict[str, object], json.loads(capsys.readouterr().out))
    live_gate = cast(dict[str, object], payload["live_gate"])
    blockers = cast(tuple[str, ...] | list[str], live_gate["blockers"])
    assert "confirm_live" not in blockers
    assert "explicit_user_request" in blockers
    assert live_gate["status"] == "LIVE_ORDER_BLOCKED"


def test_cli_command_catalog_has_unique_names_and_safe_aliases() -> None:
    canonical_names = [spec.canonical for spec in COMMAND_SPECS]
    assert len(canonical_names) == len(set(canonical_names))
    names = available_command_names()
    assert len(names) == len(set(names))
    assert canonical_command("summary") == "status"
    assert canonical_command("research") == "research-public"
    assert canonical_command("validate") == "validate-research"
    assert canonical_command("ops") == "opportunities"
    assert canonical_command("backtests") == "validation-summary"
    assert canonical_command("live-preview") == "live-preview-spot"
    assert canonical_command("runtime-refresh") == "runtime-research-refresh-once"
    assert canonical_command("virtual-market-once") == "virtual-market-once"
    assert canonical_command("virtual-runtime-once") == "virtual-market-once"
    assert canonical_command("virtual-runtime") == "virtual-market-once"
    assert canonical_command("virtual-market-soak") == "virtual-market-soak"
    assert canonical_command("virtual-runtime-soak") == "virtual-market-soak"
    assert (
        canonical_command("virtual-market-retrieval-eval")
        == "virtual-market-retrieval-eval"
    )
    assert canonical_command("privacy-boundary") == "privacy-boundary"
    assert canonical_command("qaqc-audit") == "quality-system-audit"
    assert canonical_command("agent-stack-audit") == "agent-stack-audit"
    assert canonical_command("oek-audit") == "oek-gap-analysis"
    assert canonical_command("vnext-audit") == "vnext-gap-audit"
    assert canonical_command("gap-audit") == "vnext-gap-audit"
    assert canonical_command("paper-soak-readiness") == "virtual-market-paper-soak"
    assert canonical_command("scan", "spot") == "scan-spot"
    assert canonical_command("scan", "futures") == "scan-futures"
    assert canonical_command("scan", "all") == "scan-all"
    assert canonical_command("scan", "margin") == "scan-unknown"


def test_live_place_cli_accepts_only_authorization_envelope_reference() -> None:
    parsed = parse_arguments(
        ["live-place-spot", "--authorization-id", "authorization-1"]
    )
    assert parsed.authorization_id == "authorization-1"

    with pytest.raises(SystemExit):
        parse_arguments(
            [
                "live-place-spot",
                "--approval-id",
                "approval-1",
                "--preview-hash",
                "a" * 64,
            ]
        )


def test_cli_documentation_tracks_command_catalog() -> None:
    docs_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "contracts"
        / "interface_contract_cli_command.md"
    )
    docs = docs_path.read_text(encoding="utf-8")
    marker_start = "<!-- CLI_COMMAND_TABLE_START -->"
    marker_end = "<!-- CLI_COMMAND_TABLE_END -->"
    assert marker_start in docs
    assert marker_end in docs
    table = docs.split(marker_start, maxsplit=1)[1].split(marker_end, maxsplit=1)[0]

    documented_commands = []
    for line in table.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not cells[0].startswith("`"):
            continue
        documented_commands.append(cells[0].strip("`"))

    assert documented_commands == [spec.canonical for spec in COMMAND_SPECS]
    for spec in COMMAND_SPECS:
        assert spec.summary in table


def test_commands_cli_lists_grouped_user_friendly_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["commands"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "commands"
    assert "validation" in payload["groups"]
    assert "portfolio" in payload["groups"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    assert main(["help", "validation", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "[validation]" in output
    assert "validation-summary" in output
    assert "LIVE_ORDER_BLOCKED" not in output


def test_dge_cli_commands_are_report_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["dge-rules"]) == 0
    rules = json.loads(capsys.readouterr().out)
    assert rules["command"] == "dge-rules"
    assert rules["rule_count"] > 0
    assert rules["execution_allowed"] is False
    assert rules["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    assert main(["dge-shadow-rules"]) == 0
    shadow = json.loads(capsys.readouterr().out)
    assert shadow["active_policy_mutation_allowed"] is False
    assert shadow["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    assert main(["dge-replay"]) == 2
    replay = json.loads(capsys.readouterr().out)
    assert replay["status"] == "NON_REPRODUCIBLE"
    assert replay["blockers"] == ["DGE_DECISION_ID_REQUIRED"]


def test_dge_replay_payload_preserves_replay_blockers_and_type_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DgeReplayResult(
        decision_id="dge:missing",
        status="NON_REPRODUCIBLE",
        checked_fields=(),
        blocker="DGE_REPLAY_RECORD_NOT_FOUND",
    )
    monkeypatch.setattr(
        "ai4binance.cli.dge.replay_dge_decision",
        lambda root, decision_id: result,
    )

    payload = dge_replay_payload(
        decision_id=" dge:missing ",
        repository_root=tmp_path,
    )

    assert payload["command"] == "dge-replay"
    assert payload["status"] == "NON_REPRODUCIBLE"
    assert payload["blockers"] == ("DGE_REPLAY_RECORD_NOT_FOUND",)
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    monkeypatch.setattr(
        "ai4binance.cli.dge.replay_dge_decision",
        lambda root, decision_id: ("not", "a", "mapping"),
    )
    with pytest.raises(TypeError, match="DGE replay payload"):
        dge_replay_payload(decision_id="dge:bad", repository_root=tmp_path)


def test_dge_shadow_rules_helper_is_fail_closed() -> None:
    payload = dge_shadow_rules_payload()

    assert payload["command"] == "dge-shadow-rules"
    assert payload["active_policy_mutation_allowed"] is False
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["blockers"] == ("HUMAN_REVIEW_REQUIRED_FOR_RULE_PROMOTION",)


def test_privacy_boundary_cli_reports_redacted_findings(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_marker = "LOCAL-DEVICE-ALPHA"
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs/archive/reference_local_computer_profile.md").write_text(
        f"Device: {profile_marker}\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "leak.md").write_text(
        f"Copied local detail: {profile_marker}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["privacy-boundary"]) == 2

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["command"] == "privacy-boundary"
    assert payload["status"] == "BLOCKED"
    assert payload["report"]["finding_count"] == 1
    assert payload["report"]["findings"][0]["file_path"] == "docs/leak.md"
    assert "PERSONAL_INFO_OUTSIDE_COMPUTER_MD" in payload["blockers"]
    assert profile_marker not in output
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_summary_alias_and_text_output_remain_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["summary", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "Status:" in output
    assert "NO_TRADE" in output
    assert "LIVE_ORDER_BLOCKED" in output
    assert "BOUNDED_AUTONOMOUS_SIMULATION" in output


def test_backtest_runtime_economics_command_reports_fail_closed_cuda_visibility(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        GpuResourceGovernor,
        "collect_telemetry",
        lambda self: GpuTelemetrySnapshot.unavailable(source="torch-unavailable"),
    )

    assert main(["backtest-runtime-economics"]) == 2
    payload = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert payload["command"] == "backtest-runtime-economics"
    assert payload["status"] == "WATCHLIST"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["gpu_available"] is False
    assert payload["gpu_requested"] is False
    assert payload["gpu_used"] is False
    assessment = cast(dict[str, object], payload["telemetry_assessment"])
    assert assessment["healthy"] is False
    assert assessment["source_label"] == "torch-unavailable"
    assert assessment["blockers"] == ["CUDA_UNAVAILABLE"]
    benchmark = cast(dict[str, object], payload["benchmark"])
    blockers = cast(tuple[str, ...] | list[str], payload["blockers"])
    assert benchmark["candle_count"] == 24
    assert benchmark["cuda_source"] == "torch-unavailable"
    assert "POWER_THERMAL_REVIEW_REQUIRED" in blockers
    assert "BACKTEST_RUNTIME_COST_MEASUREMENT_REQUIRED" in blockers

    text = render_payload(
        payload,
        output_format="text",
        command="backtest-runtime-economics",
    )
    assert "Backtest runtime economics:" in text
    assert "- gpu_available: False" in text
    assert "- gpu_requested: False" in text
    assert "- telemetry_assessment: False torch-unavailable" in text
    assert "['CUDA_UNAVAILABLE']" in text


def test_backtests_alias_uses_validation_summary_payload(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    run_card = validation_root / "HOTUSDT" / "1h" / "trend.run-card.json"
    run_card.parent.mkdir(parents=True)
    run_card.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": ["WEAK_OOS_FOLD_CONSISTENCY"],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend:1h",
                "metrics": [["net_return", 0.0]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:1",
                "symbol": "HOTUSDT",
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(validation_root))

    assert main(["backtests", "--symbol", "HOTUSDT"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["run_count"] == 1
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_opportunities_cli_succeeds_when_research_radar_is_active(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    run_card = validation_root / "HOTUSDT" / "1h" / "trend.run-card.json"
    run_card.parent.mkdir(parents=True)
    run_card.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": ["WEAK_OOS_FOLD_CONSISTENCY"],
                "created_at": "2026-08-03T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:1h",
                "metrics": [["net_return", 0.01]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:watchlist",
                "symbol": "HOTUSDT",
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    outlook = tmp_path / "market-outlook" / "runtime-state.json"
    outlook.parent.mkdir(parents=True)
    outlook.write_text(
        json.dumps(
            {
                "blockers": ["NO_READY_CANDIDATE"],
                "pro_trend_direction": "BULLISH",
                "setups_on_radar": ["breakout_retest"],
                "status": "PARTIAL",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(validation_root))
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))

    assert main(["opportunities", "--symbol", "HOTUSDT"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ACTIVE"
    assert payload["opportunity_generation_allowed"] is True
    assert payload["execution_allowed"] is False
    assert payload["report_version"] == "2.0"
    assert payload["opportunity_report_v2"]["report_version"] == "2.0"
    assert (
        payload["opportunity_report_v2"]["live_eligibility_status"]
        == "LIVE_ORDER_BLOCKED"
    )
    assert "NO_READY_CANDIDATE" in payload["execution_blockers"]
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_cli_text_renderer_covers_validation_opportunities_and_generic() -> None:
    validation_text = render_payload(
        {
            "command": "validation-summary",
            "summary": {
                "symbol": "HOTUSDT",
                "run_count": 2,
                "research_only_count": 2,
                "staged_candidate_count": 0,
                "top_blockers": (("WEAK_OOS", 2), ("LOW_TRADES", 1)),
            },
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        output_format="text",
        command="validation-summary",
    )
    assert "Validation summary: HOTUSDT" in validation_text
    assert "WEAK_OOS=2" in validation_text

    virtual_queue_text = render_payload(
        {
            "command": "virtual-improvement-research-queue",
            "snapshot_id": "snapshot:queue:publish:1",
            "status": "READY",
            "items": (
                {
                    "priority": "P0",
                    "affected_component": "virtual_runtime.breakout",
                    "candidate_id": "improvement:snapshot:queue:publish:1:breakout",
                },
            ),
            "blockers": (),
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        output_format="text",
        command="virtual-improvement-research-queue",
    )
    assert "Virtual improvement queue: snapshot:queue:publish:1" in virtual_queue_text
    assert "- status: READY" in virtual_queue_text
    assert "- staged_candidates: 1" in virtual_queue_text

    opportunities_text = render_payload(
        {
            "command": "opportunities",
            "inbox": {
                "symbol": "HOTUSDT",
                "blockers": ("NO_READY_CANDIDATE",),
                "generation_status": "ACTIVE",
                "research_loop_allowed": True,
                "research_blockers": (),
                "execution_blockers": ("NO_READY_CANDIDATE",),
                "next_safe_actions": ("PLAN_NEXT_EVIDENCE_REFRESH",),
                "items": (
                    {
                        "market": "SPOT",
                        "timeframe": "1h",
                        "setup_name": "trend_continuation",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 76.0,
                        "confidence": 0.62,
                    },
                ),
            },
            "opportunity_report_v2": {
                "report_version": "2.0",
                "sections": {
                    "top_opportunities": (),
                    "confirmation_pending": (
                        {
                            "symbol": "HOTUSDT",
                            "grade": "B",
                            "lifecycle_state": "CONFIRMATION_PENDING",
                            "setup_name": "trend_continuation",
                            "timeframe": "1h",
                            "confirmation_gaps": ("ENTRY_TRIGGER_MISSING",),
                            "validation_gaps": ("VALIDATION_GATE_REQUIRED",),
                            "next_safe_action": (
                                "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"
                            ),
                        },
                    ),
                    "setup_forming": (),
                    "validation_ladder": (),
                    "rejected_or_lost": (),
                },
                "snapshot_diff": {
                    "new_candidates": (),
                    "upgraded_candidates": (),
                    "downgraded_candidates": (),
                    "still_pending": ("HOTUSDT",),
                },
                "next_safe_actions": (
                    {"action": "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"},
                ),
            },
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        output_format="text",
        command="opportunities",
    )
    assert "OPPORTUNITY RADAR" in opportunities_text
    assert "Visible Items: 1" in opportunities_text
    assert "Trading: NO_TRADE" in opportunities_text
    assert "Execution Blockers: NO_READY_CANDIDATE" in opportunities_text
    assert "trend_continuation" in opportunities_text

    research_text = render_payload(
        {
            "command": "research-public",
            "symbol": "HOTUSDT",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "research_stages": (
                {"name": "acquisition"},
                {"name": "analysis"},
            ),
            "virtual_runtime_decision": {
                "status": "ORDER_READY",
                "eligibility": {
                    "status": "ELIGIBLE",
                },
                "blockers": (),
            },
        },
        output_format="text",
        command="research-public",
    )
    assert "Research public: HOTUSDT" in research_text
    assert "virtual_runtime_decision: ORDER_READY" in research_text
    assert "virtual_runtime_eligibility: ELIGIBLE" in research_text
    assert "virtual_runtime_live: LIVE_ORDER_BLOCKED" in research_text

    generic_text = render_payload(
        {
            "command": "accounting-status",
            "status": "BLOCKED",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "promotion_status": "RESEARCH_ONLY",
            "blockers": ("ACCOUNTING_FILE_MISSING",),
        },
        output_format="text",
        command="accounting-status",
    )
    assert "accounting-status" in generic_text
    assert "ACCOUNTING_FILE_MISSING" in generic_text

    commands_text = render_payload(
        command_catalog_payload("portfolio"),
        output_format="text",
        command="commands",
    )
    assert "[portfolio]" in commands_text
    assert "[core]" not in commands_text


def test_cli_renderer_json_default_is_machine_readable() -> None:
    rendered = render_payload({"command": "status", "blockers": ()})
    assert json.loads(rendered) == {"blockers": [], "command": "status"}


def test_agents_command_lists_governed_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["agents"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent_count"] == 49
    assert payload["hard_gate_eligible_count"] == 0
    assert payload["live_eligible_count"] == 0
    assert payload["execution_allowed"] is False
    names = {agent["name"] for agent in payload["agents"]}
    assert {
        "trend",
        "memory_advisory",
        "confluence",
        "risk",
        "validation",
        "learning",
        "qaqc_agent",
    } <= names


def test_agentic_skills_command_reports_catalog_and_safe_recommendation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["agentic-skills"]) == 0
    catalog_payload = json.loads(capsys.readouterr().out)
    assert catalog_payload["pattern_count"] == 9
    contract = catalog_payload["advanced_agent_operating_contract"]
    assert contract["orchestration"] == "MULTI_STEP_WORKFLOWS"
    assert contract["automation_scope"] == "REPETITIVE_OPERATIONS"
    assert contract["execution_scope"] == "END_TO_END_OPERATIONS"
    assert "EXPLICIT_POLICY_BOUNDARIES" in contract["guardrails"]
    assert "DECISION_RECORDS" in contract["auditable_traceability"]
    assert contract["human_approval_controls"]["mode"] == "HUMAN_IN_THE_LOOP"
    assert (
        contract["human_approval_controls"]["required_at"] == "CRITICAL_DECISION_POINTS"
    )
    assert catalog_payload["execution_allowed"] is False
    assert catalog_payload["promotion_status"] == "RESEARCH_ONLY"
    assert catalog_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    assert (
        main(
            [
                "agentic-skills",
                "--task",
                "Customer complaint comes in",
                "--risk-domain",
                "customer_promise",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    plan = payload["recommended_plan"]
    assert plan["selected_pattern"]["pattern_id"] == "human_in_the_loop"
    assert "HUMAN_REVIEW_REQUIRED" in plan["blockers"]
    assert plan["execution_allowed"] is False
    assert plan["promotion_status"] == "RESEARCH_ONLY"
    assert plan["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_skills_audit_command_reports_read_only_blockers(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "risky-skill"
    skill_dir.mkdir()
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            (
                "---",
                "name: risky-skill",
                "description: Use when reviewing skills.",
                "allowed-tools: Bash(git:*) Read",
                "---",
                "# Risky Skill",
            )
        ),
        encoding="utf-8",
    )

    assert main(["skills-audit", "--skills-root", str(tmp_path)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "skills-audit"
    assert payload["report"]["skill_count"] == 1
    assert "SKILL_SCRIPT_REVIEW_REQUIRED" in payload["blockers"]
    assert payload["execution_allowed"] is False
    assert payload["installation_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    assert (
        main(["skills-audit", "--skills-root", str(tmp_path), "--format", "text"]) == 2
    )
    output = capsys.readouterr().out
    assert "Agent Skills audit" in output
    assert "SKILL_SCRIPT_REVIEW_REQUIRED" in output


def test_enterprise_intake_cli_outputs_summary_only_directive(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text(
        "CODEX_PROMPT: apply holding governance. SECRET=hidden-value",
        encoding="utf-8",
    )

    assert main(["enterprise-intake", "--prompt-file", str(prompt_file)]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["command"] == "enterprise-intake"
    assert payload["status"] == "READY_FOR_GENERAL_MANAGER_REVIEW"
    assert payload["prompt"]["raw_prompt_visibility"] == "GENERAL_MANAGER_ONLY"
    assert payload["prompt"]["department_visibility"] == "DEPARTMENT_SUMMARY"
    assert "hidden-value" not in output
    assert "CODEX_PROMPT" not in output
    assert payload["directive"]["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_enterprise_intake_cli_fails_closed_without_prompt_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["enterprise-intake"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["blockers"] == ["ENTERPRISE_PROMPT_FILE_REQUIRED"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_quality_system_audit_cli_reports_quality_department_review(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["quality-system-audit"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "quality-system-audit"
    assert payload["status"] == "PASSED"
    assert payload["blockers"] == []
    assert payload["report"]["manager_id"] == "QualityDepartmentManager"
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_qaqc_audit_cli_alias_runs_quality_system_audit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["qaqc-audit", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "quality-system-audit" in output
    assert "PASSED" in output
    assert "LIVE_ORDER_BLOCKED" in output


def test_agent_stack_audit_cli_reports_governed_layers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["agent-stack-audit", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "Agent stack audit" in output
    assert "RAG: PASSED" in output
    assert "GOVERNANCE_AUTHORITY" in output
    assert "LIVE_ORDER_BLOCKED" in output


def test_oek_gap_analysis_cli_checks_safe_change_manifest(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    change_file = tmp_path / "oek-change.json"
    change_file.write_text(
        json.dumps(
            {
                "change_id": "oek-change:skill:001",
                "change_kind": "SKILL",
                "subject_ref": "skill:quality_gate-loop",
                "changed_paths": [".agents/skills/quality_gate-loop/SKILL.md"],
                "summary": "Refresh advisory-only quality gate skill.",
                "evidence_refs": ["test:tests/test_skill_linter.py"],
                "declared_controls": [
                    "OEK_CONSTITUTION_COMPLIANCE",
                    "HUMAN_REVIEW_REQUIRED",
                    "LIVE_ORDER_BLOCKED",
                    "AUDIT_TRAIL_REQUIRED",
                    "SKILLS_AUDIT_REQUIRED",
                    "NO_INSTALL_OR_EXECUTE_WITHOUT_REVIEW",
                    "SUPPLY_CHAIN_REVIEW_REQUIRED",
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert main(["oek-gap-analysis", "--change-file", str(change_file)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "oek-gap-analysis"
    assert payload["status"] == "PASSED"
    assert payload["blockers"] == []
    assert payload["report"]["change_kind"] == "SKILL"
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_oek_gap_analysis_cli_fails_closed_without_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["oek-audit"]) == 2


def test_virtual_market_paper_soak_cli_writes_readiness_artifact(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["virtual-market-paper-soak", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "virtual-market-paper-soak"
    assert payload["status"] == "READY"
    assert payload["report"]["stage"] == "PAPER_SOAK"
    assert payload["report"]["blockers"] == [
        "USER_APPROVAL_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    ]
    assert payload["report"]["promotion_status"] == "RESEARCH_ONLY"
    assert payload["report"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert Path(payload["artifact_path"]).exists()
    assert Path(payload["artifact_path"]) == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "virtual-market"
        / "paper-soak"
        / "latest.json"
    )


def test_virtual_market_soak_cli_writes_boundary_soak_artifact(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["virtual-market-soak", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "virtual-market-soak"
    assert payload["status"] == "READY"
    assert payload["sample_count"] == 3
    assert payload["stable_gate_hashes"] is True
    assert payload["gate_payload"]["execution_surface"] == "VIRTUAL_MARKET"
    assert payload["gate_payload"]["live_order_allowed"] is False
    assert payload["gate_payload"]["execution_allowed"] is False
    assert payload["gate_payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert Path(payload["artifact_path"]).exists()
    assert Path(payload["artifact_path"]) == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "virtual-market"
        / "runtime-soak"
        / "latest.json"
    )


def test_virtual_market_retrieval_eval_cli_writes_eval_artifact(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_dir = tempfile.mkdtemp()
    root = Path(temp_dir)
    original_cwd = Path.cwd()
    try:
        monkeypatch.chdir(root)
        (root / "docs").mkdir()
        (root / "docs" / "btc.md").write_text(
            "VIRTUAL_MARKET governance blockers remain research only.\n",
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "virtual-market-retrieval-eval",
                    "--query",
                    "VIRTUAL_MARKET governance",
                ]
            )
            == 0
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "virtual-market-retrieval-eval"
        assert payload["status"] == "READY"
        assert payload["query"] == "VIRTUAL_MARKET governance"
        assert payload["evidence_quality"]["status"] == "RESEARCH_ONLY_RAG_EVIDENCE"
        assert payload["evidence_quality"]["citation_coverage"] == 1.0
        assert payload["governed_retrieval"]["status"] == "RESEARCH_ONLY_RETRIEVAL"
        assert payload["governed_retrieval"]["final_authority"] == "NONE"
        assert (
            payload["governed_retrieval"]["advisory_fusion_status"] == "NOT_REQUESTED"
        )
        assert payload["execution_allowed"] is False
        assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
        assert Path(payload["index_path"]).exists()
        assert Path(payload["production_artifact_path"]).exists()
        assert Path(payload["artifact_path"]).exists()
        assert Path(payload["artifact_path"]) == (
            root
            / "runtime"
            / "artifacts"
            / "virtual-market"
            / "retrieval-eval"
            / "latest.json"
        )
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize(
    ("content", "blocker"),
    [
        ("not-json", "OEK_CHANGE_FILE_INVALID"),
        ("[]", "OEK_CHANGE_FILE_SHAPE_INVALID"),
        ('{"change_id":"missing-required-fields"}', "OEK_CHANGE_MANIFEST_INVALID"),
    ],
)
def test_oek_gap_analysis_cli_fails_closed_for_invalid_manifest_file(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    content: str,
    blocker: str,
) -> None:
    change_file = tmp_path / "invalid-oek-change.json"
    change_file.write_text(content, encoding="utf-8")

    assert main(["oek-gap-analysis", "--change-file", str(change_file)]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "oek-gap-analysis"
    assert payload["status"] == "BLOCKED"
    assert payload["blockers"] == [blocker]
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def public_snapshot() -> MarketSnapshot:
    now = datetime(2026, 7, 11, 12, tzinfo=UTC)
    candles = tuple(
        OHLCVCandle(
            timestamp=now - timedelta(hours=offset),
            open=Decimal("1"),
            high=Decimal("1.1"),
            low=Decimal("0.9"),
            close=Decimal("1.05"),
            volume=Decimal("100"),
        )
        for offset in (2, 1)
    )
    return MarketSnapshot(
        snapshot_id="public-snapshot-1",
        created_at=now,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": candles},
        latest_price=Decimal("1.05"),
        bid=Decimal("1.049"),
        ask=Decimal("1.051"),
        spread=Decimal("0.002"),
        exchange_filters={"PRICE_FILTER": {"tickSize": "0.001"}},
        data_freshness={"1h": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"trading_status": "TRADING"},
    )


class StubAcquisition:
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        assert symbol == "HOTUSDT"
        assert timeframes == ("1h",)
        return public_snapshot()


class FailingAcquisition:
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        del symbol, timeframes
        raise ExchangeTransportError("private transport detail")


def test_analyze_public_runs_orchestrator_and_writes_audit(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')
    monkeypatch.setenv("AI4BINANCE_CANDLE_LIMIT", "2")
    monkeypatch.setenv("AI4BINANCE_MINIMUM_CLOSED_CANDLES", "2")
    monkeypatch.setenv("AI4BINANCE_AUDIT_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    assert main(["analyze-public"], public_acquisition=StubAcquisition()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshot_id"] == "public-snapshot-1"
    assert payload["market_outlook"]["status"] == "PARTIAL"
    assert payload["opportunity_radar"]["status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["opportunity_radar"]["execution_allowed"] is False
    assert payload["opportunity_radar"]["live_eligibility_status"] == (
        "LIVE_ORDER_BLOCKED"
    )
    assert (
        payload["opportunity_radar_telemetry"]["candidate_evaluation_duration_ms"] >= 0
    )
    assert payload["opportunity_radar_telemetry"]["source_snapshot_count"] == 1
    assert payload["opportunity_radar_telemetry"]["candidate_count"] == 1
    radar_path = tmp_path / "opportunity-radar" / "latest.json"
    radar_state = json.loads(radar_path.read_text(encoding="utf-8"))
    assert radar_state["source_snapshot_ids"] == ["public-snapshot-1"]
    assert radar_state["candidate_count"] == 1
    assert (
        "CANONICAL_MTF_SNAPSHOT_INCOMPLETE:15m,4h"
        in (radar_state["candidate_states"][0]["blockers"])
    )
    assert payload["market_outlook"]["execution_allowed"] is False
    assert payload["decision"]["decision_state"] == "NO_TRADE"
    assert payload["execution_allowed"] is False
    audit_lines = (
        (tmp_path / "analysis_events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 2


def test_analyze_public_fails_closed_without_error_detail(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')
    assert main(["analyze-public"], public_acquisition=FailingAcquisition()) == 2
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["decision_state"] == "NO_TRADE"
    assert payload["blockers"] == ["PUBLIC_DATA_ACQUISITION_FAILED"]
    assert "private transport detail" not in output


def test_research_public_reports_stages_and_writes_workflow_audit(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')
    monkeypatch.setenv("AI4BINANCE_CANDLE_LIMIT", "2")
    monkeypatch.setenv("AI4BINANCE_MINIMUM_CLOSED_CANDLES", "2")
    monkeypatch.setenv("AI4BINANCE_AUDIT_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))

    assert main(["research-public"], public_acquisition=StubAcquisition()) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert "virtual_runtime_decision" in payload
    assert payload["virtual_runtime_decision"] is None
    assert [stage["name"] for stage in payload["research_stages"]] == [
        "acquisition",
        "analysis",
        "strategy",
        "risk",
        "virtual_market_execution",
        "learning",
    ]
    audit_lines = (
        (tmp_path / "research_events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 1


def test_virtual_runtime_decision_payload_helper_normalizes_fallback_shape() -> None:
    eligibility = SimpleNamespace(
        status=SimpleNamespace(value="ELIGIBLE"),
        blockers=(),
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    decision = SimpleNamespace(
        status=SimpleNamespace(value="ORDER_READY"),
        eligibility=eligibility,
        trade_intent=None,
        portfolio_before=None,
        portfolio_after=None,
        audit_refs=("snapshot", "decision", "portfolio"),
        halt_review=None,
        halted=False,
    )

    payload = cast(
        dict[str, object], cli_shared.virtual_runtime_decision_payload(decision)
    )
    eligibility_payload = cast(dict[str, object], payload["eligibility"])

    assert payload["status"] == "ORDER_READY"
    assert eligibility_payload["status"] == "ELIGIBLE"
    assert eligibility_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["audit_refs"] == ("snapshot", "decision", "portfolio")
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_shared_cli_helpers_export_only_the_shared_contract() -> None:
    assert cli_shared.__all__ == (
        "virtual_market_gate_payload",
        "virtual_runtime_decision_payload",
    )
    assert cli_shared.__dir__() == list(cli_shared.__all__)


def test_status_preserves_the_public_acquisition_builder_alias() -> None:
    assert status_cli.build_public_acquisition is cli_shared.build_public_acquisition


def test_whale_fusion_research_cli_is_safe_without_provider_evidence(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')
    monkeypatch.setenv("AI4BINANCE_CANDLE_LIMIT", "2")
    monkeypatch.setenv("AI4BINANCE_MINIMUM_CLOSED_CANDLES", "2")
    monkeypatch.setenv("AI4BINANCE_AUDIT_DIRECTORY", str(tmp_path))
    cycle = WhaleFusionCycle("public-snapshot-1", "HOTUSDT", "HOT")

    assert (
        main(
            ["whale-fusion-research"],
            public_acquisition=StubAcquisition(),
            whale_fusion_cycle=cycle,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["fusion"]["fusion_score"] == "50.0"
    assert "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT" in payload["blockers"]
    assert payload["whale_agent"]["status"] == "INSUFFICIENT_DATA"
    assert payload["decision"]["decision_state"] == "NO_TRADE"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_archive_public_writes_market_only_parquet(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_MARKET_HISTORY_LOCAL_CANDLES", "false")
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')
    monkeypatch.setenv("AI4BINANCE_CANDLE_LIMIT", "2")
    monkeypatch.setenv("AI4BINANCE_MINIMUM_CLOSED_CANDLES", "2")
    monkeypatch.setenv("AI4BINANCE_DATASET_DIRECTORY", str(tmp_path))

    assert main(["archive-public"], public_acquisition=StubAcquisition()) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["wallet_data_included"] is False
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["manifests"][0]["row_count"] == 2
    assert (tmp_path / "HOTUSDT" / "1h.parquet").exists()


def test_validate_research_fails_closed_without_archive(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_DATASET_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')

    assert main(["validate-research"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "BTCUSDT"
    assert payload["validation_status"] == "RESEARCH_ONLY"
    assert payload["blockers"] == ["VALIDATION_DATA_UNAVAILABLE_OR_INVALID"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_crew_plan_reports_btcusdt_biweekly_validation_task(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI4BINANCE_TIMEFRAMES", '["1h"]')

    assert main(["crew-plan"]) == 0

    payload = json.loads(capsys.readouterr().out)
    task = payload["biweekly_validation_task"]
    assert payload["validation_symbol"] == "BTCUSDT"
    assert task["task_id"] == "btcusdt_biweekly_backtest_tuning"
    assert task["symbol"] == "BTCUSDT"
    assert task["cadence"] == "BIWEEKLY"
    assert task["interval_days"] == 14
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_second_brain_cli_builds_index_and_html_ui(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "btc.md").write_text(
        "BTCUSDT opportunity validation remains research only.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "AI4BINANCE_SECOND_BRAIN_INDEX_PATH",
        str(tmp_path / "state" / "second-brain-index.json"),
    )

    assert main(["second-brain", "--query", "BTCUSDT opportunity", "--ui"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["hits"][0]["source_uri"] == "docs/btc.md"
    assert payload["evidence_quality"]["status"] == "RESEARCH_ONLY_RAG_EVIDENCE"
    assert payload["evidence_quality"]["citation_coverage"] == 1.0
    assert payload["governed_retrieval"]["status"] == "RESEARCH_ONLY_RETRIEVAL"
    assert payload["governed_retrieval"]["final_authority"] == "NONE"
    assert payload["governed_retrieval"]["advisory_fusion_status"] == "NOT_REQUESTED"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert Path(payload["index_path"]).exists()
    assert Path(payload["production_artifact_path"]).exists()
    assert Path(payload["ui_path"]).exists()


def test_lean_governance_cli_reports_operational_excellence_pillars(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "runtime" / "tmp" / "pytest" / "lean-governance").mkdir(parents=True)

    assert main(["lean-governance"]) == 0

    payload = json.loads(capsys.readouterr().out)
    pillars = {item["pillar"] for item in payload["assessments"]}
    assert pillars == {"5S", "HOSHIN_KANRI", "KAIZEN", "SIX_SIGMA", "POKA_YOKE"}
    assert payload["mode"] == "LEAN_GOVERNANCE_REVIEW"
    assert payload["agent"]["agent_id"] == "qaqc_agent"
    assert payload["agent"]["display_name"] == "QAQC-Agent"
    assert payload["agent"]["authority"] == "GOVERNED_EDITING_AND_IMPROVEMENT_REVIEW"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert "FIVE_S_SHINE_STALE_TEMP_REVIEW_REQUIRED" in payload["blockers"]
    assert "POKA_YOKE_CHECK_MISSING:TECHNICAL_QUALITY_PASS" in payload["blockers"]


def test_qaqc_agent_cli_alias_reports_named_agent(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["qaqc-agent"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "QAQC_AGENT_REVIEW"
    assert payload["agent"]["display_name"] == "QAQC-Agent"
    assert "KAIZEN" in payload["agent"]["methods"]
    assert "SIX_SIGMA" in payload["agent"]["methods"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_runtime_once_blocks_before_market_access_without_credentials(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "runtime.json"
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(state_path))

    assert main(["runtime-once"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "DEGRADED"
    assert payload["spot"]["action"] == "NO_TRADE"
    assert payload["futures"]["action"] == "NO_TRADE"
    assert payload["blockers"] == [
        "SPOT_WALLET_SERVICE_UNAVAILABLE",
        "FUTURES_ACCOUNT_SERVICE_UNAVAILABLE",
    ]
    assert payload["startup_replay"]["status"] == "READY"
    assert payload["startup_replay"]["replay"]["journal_exists"] is False
    assert payload["startup_replay"]["replay"]["event_count"] == 0
    assert "spot_wallet" not in payload
    assert "futures_account" not in payload
    assert payload["investment_management"]["recommendations"] == []
    assert payload["investment_management"]["execution_allowed"] is False
    assert state_path.exists()


def test_runtime_research_refresh_once_runs_pipeline_in_one_command(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_cli,
        "_refresh_runtime_research_feeds",
        lambda settings: {
            "status": "READY",
            "fetched_at": "2026-08-04T20:40:00+00:00",
            "counts": {
                "news": 3,
                "social": 3,
                "content": 3,
                "technology": 3,
            },
            "domains": {
                "news": ("www.coindesk.com",),
                "social": ("www.reddit.com",),
                "content": ("www.coindesk.com",),
                "technology": ("github.blog",),
            },
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    monkeypatch.setattr(
        runtime_cli,
        "_run_runtime_once",
        lambda settings: (
            {
                "cycle_id": "runtime-HOTUSDT-test",
                "created_at": "2026-08-04T20:40:05+00:00",
                "state": "DEGRADED",
                "blockers": ["FUTURES_OOS_NOT_APPROVED"],
            },
            2,
        ),
    )
    monkeypatch.setattr(
        runtime_cli,
        "_validate_runtime_research_traceability",
        lambda settings: (
            {
                "status": "PASS",
                "report_path": (
                    "runtime/state/runtime_research/trace-validation-latest.json"
                ),
                "opportunity_count": 1,
                "validated_count": 1,
                "all_opportunities_traceable": True,
                "mismatch_count": 0,
                "blockers": (),
            },
            0,
        ),
    )

    assert main(["runtime-research-refresh-once"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS_WITH_RUNTIME_DEGRADED"
    assert payload["feed_refresh"]["status"] == "READY"
    assert payload["runtime_cycle"]["cycle_id"] == "runtime-HOTUSDT-test"
    assert payload["trace_validation"]["all_opportunities_traceable"] is True
    assert payload["execution_allowed"] is False


def test_runtime_research_refresh_once_blocks_when_trace_validation_fails(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_cli,
        "_refresh_runtime_research_feeds",
        lambda settings: {
            "status": "READY",
            "fetched_at": "2026-08-04T20:40:00+00:00",
            "counts": {
                "news": 3,
                "social": 3,
                "content": 3,
                "technology": 3,
            },
            "domains": {
                "news": ("www.coindesk.com",),
                "social": ("www.reddit.com",),
                "content": ("www.coindesk.com",),
                "technology": ("github.blog",),
            },
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    monkeypatch.setattr(
        runtime_cli,
        "_run_runtime_once",
        lambda settings: (
            {
                "cycle_id": "runtime-HOTUSDT-test",
                "created_at": "2026-08-04T20:40:05+00:00",
                "state": "READY",
                "blockers": [],
            },
            0,
        ),
    )
    monkeypatch.setattr(
        runtime_cli,
        "_validate_runtime_research_traceability",
        lambda settings: (
            {
                "status": "BLOCKED",
                "report_path": (
                    "runtime/state/runtime_research/trace-validation-latest.json"
                ),
                "opportunity_count": 2,
                "validated_count": 1,
                "all_opportunities_traceable": False,
                "mismatch_count": 1,
                "blockers": ("TRACE_EVIDENCE_ID_NOT_FOUND",),
            },
            2,
        ),
    )

    assert main(["runtime-research-refresh-once"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["trace_validation"]["status"] == "BLOCKED"
    assert "TRACE_EVIDENCE_ID_NOT_FOUND" in payload["blockers"]


@pytest.mark.parametrize(
    "command_name",
    ["virtual-market-once", "virtual-runtime-once", "virtual-runtime"],
)
def test_virtual_runtime_once_reports_canonical_simulation_boundary(
    command_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([command_name]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "virtual-market-once"
    assert payload["execution_surface"] == "VIRTUAL_MARKET"
    assert payload["automation_mode"] == "BOUNDED_AUTONOMOUS_SIMULATION"
    assert payload["manual_confirmation_required"] is False
    assert payload["virtual_simulation_allowed"] is True
    assert payload["external_order_allowed"] is False
    assert payload["live_order_allowed"] is False
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert "LIVE_ORDER_BLOCKED" in payload["blockers"]

    text = render_payload(
        payload,
        output_format="text",
        command=command_name,
    )
    assert "Virtual market probe" in text
    assert "execution_surface: VIRTUAL_MARKET" in text
    assert "automation_mode: BOUNDED_AUTONOMOUS_SIMULATION" in text
    assert "execution_allowed: False" in text
    assert "promotion_status: RESEARCH_ONLY" in text
    assert "LIVE_ORDER_BLOCKED" in text


def test_virtual_market_daemon_runs_bounded_cycles_and_persists_safe_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_path = tmp_path / "state" / "runtime.json"
    settings = Settings(
        runtime_state_path=state_path,
        runtime_cycle_interval_seconds=5,
    )
    observed = iter(
        (
            datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
            datetime(2026, 9, 12, 12, 1, tzinfo=UTC),
        )
    )
    sleeps: list[float] = []
    calls: list[object] = []
    acquisition = cast(SnapshotAcquirer, object())

    def run_cycle(_settings: Settings, source: object) -> int:
        calls.append(source)
        return 0

    assert (
        runtime_cli.run_virtual_market_daemon(
            settings,
            max_cycles=2,
            public_acquisition=acquisition,
            cycle_runner=run_cycle,
            sleeper=sleeps.append,
            clock=lambda: next(observed),
        )
        == 0
    )

    payload = json.loads(
        state_path.with_name("virtual-market.json").read_text(encoding="utf-8")
    )
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == [acquisition, acquisition]
    assert sleeps == [5]
    assert len(output) == 2
    assert payload["status"] == "RUNNING"
    assert payload["pid"] > 0
    assert payload["cycle_count"] == 2
    assert payload["cycle_exit_code"] == 0
    assert payload["cycle_blockers"] == []
    assert payload["execution_surface"] == "VIRTUAL_MARKET"
    assert payload["automation_mode"] == "BOUNDED_AUTONOMOUS_SIMULATION"
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["execution_allowed"] is False
    assert payload["external_order_allowed"] is False
    assert payload["live_order_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert not state_path.with_name("virtual-market.lock").exists()


def test_virtual_market_daemon_is_an_internal_startup_command() -> None:
    parsed = parse_arguments(["virtual-market-daemon", "--max-cycles", "1"])

    assert parsed.command == "virtual-market-daemon"
    assert parsed.max_cycles == 1
    assert "virtual-market-daemon" not in available_command_names()


def test_virtual_market_research_cycle_persists_both_wallets_and_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        timeframes=("1h",),
        candle_limit=2,
        minimum_closed_candles=2,
        audit_directory=tmp_path / "runtime" / "logs",
        evidence_artifact_directory=tmp_path / "runtime" / "artifacts",
        virtual_wallet_state_path=(
            tmp_path / "runtime" / "state" / "virtual-market" / "wallets.json"
        ),
        virtual_wallet_ledger_path=(
            tmp_path / "runtime" / "logs" / "virtual-wallet-movements.jsonl"
        ),
    )
    cycle_report: dict[str, object] = {}

    assert (
        runtime_cli._run_virtual_market_research_cycle(
            settings,
            StubAcquisition(),
            cycle_report=cycle_report,
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["virtual_wallet_movement_count"] == 2
    assert payload["virtual_wallets"]["Virtual_Spot_Wallet"]["equity_usdt"] == ("1000")
    assert payload["virtual_wallets"]["Virtual_Futures_Wallet"]["equity_usdt"] == "1000"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert cycle_report["virtual_decision_status"] == "NO_ACTION"
    assert cycle_report["virtual_runtime_evaluated"] is False
    assert cycle_report["virtual_simulation_outcome"] == "PRECONDITIONS_BLOCKED"
    assert cycle_report["virtual_order_ready"] is False
    report_path = tmp_path / "runtime" / "reports" / "virtual_wallets" / "latest.md"
    assert report_path.exists()


def test_virtual_market_daemon_fails_closed_and_records_cycle_failure(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "runtime.json"
    settings = Settings(
        runtime_state_path=state_path,
        runtime_cycle_interval_seconds=5,
    )

    sleeps: list[float] = []
    assert (
        runtime_cli.run_virtual_market_daemon(
            settings,
            max_cycles=3,
            public_acquisition=cast(SnapshotAcquirer, object()),
            cycle_runner=lambda _settings, _source: 2,
            sleeper=sleeps.append,
            clock=lambda: datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        )
        == 2
    )

    payload = json.loads(
        state_path.with_name("virtual-market.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "DEGRADED"
    assert payload["pid"] > 0
    assert payload["cycle_count"] == 3
    assert payload["consecutive_failures"] == 3
    assert payload["research_status"] == "CYCLE_FAILED"
    assert sleeps == [settings.runtime_cycle_interval_seconds] * 2
    assert payload["last_success_at"] is None
    assert payload["cycle_blockers"] == ["VIRTUAL_MARKET_CYCLE_FAILED"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_virtual_market_daemon_recovers_without_process_restart(tmp_path: Path) -> None:
    settings = Settings(
        runtime_state_path=tmp_path / "runtime.json", runtime_cycle_interval_seconds=5
    )
    results = iter((2, 0))
    sleeps: list[float] = []
    assert (
        runtime_cli.run_virtual_market_daemon(
            settings,
            max_cycles=2,
            public_acquisition=cast(SnapshotAcquirer, object()),
            cycle_runner=lambda _settings, _source: next(results),
            sleeper=sleeps.append,
            clock=lambda: datetime(2026, 9, 12, 12, tzinfo=UTC),
        )
        == 0
    )
    state = json.loads((tmp_path / "virtual-market.json").read_text())
    assert state["cycle_count"] == 2
    assert state["consecutive_failures"] == 0
    assert state["last_success_at"] is not None
    assert state["last_order_ready_at"] is None
    assert state["research_status"] == "NOT_VERIFIED"
    assert sleeps == [5]
    assert state["execution_allowed"] is False


def test_virtual_market_scan_cursor_persists_and_reports_business_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.data import market_history_sync

    monkeypatch.setattr(
        market_history_sync, "read_cached_market_universe", lambda *_args: None
    )
    settings = Settings(
        symbol="BTCUSDT",
        fixed_symbols=("ETHUSDT",),
        priority_watchlist=(),
        runtime_state_path=tmp_path / "runtime.json",
        runtime_cycle_interval_seconds=5,
    )
    seen: list[str] = []

    def research_cycle(
        settings: Settings,
        _acquisition: SnapshotAcquirer,
        *,
        cycle_report: dict[str, object] | None = None,
    ) -> int:
        assert cycle_report is not None
        seen.append(settings.symbol)
        cycle_report.update(
            snapshot_id="fixture:" + settings.symbol,
            candidate_count=1,
            research_blockers=("OOS_APPROVAL_MISSING",),
            virtual_order_ready=False,
        )
        return 0

    monkeypatch.setattr(
        runtime_cli, "_run_virtual_market_research_cycle", research_cycle
    )
    for _ in range(2):
        assert (
            runtime_cli.run_virtual_market_daemon(
                settings,
                max_cycles=1,
                public_acquisition=cast(SnapshotAcquirer, object()),
            )
            == 0
        )
    assert seen == ["BTCUSDT", "ETHUSDT"]
    state = json.loads((tmp_path / "virtual-market.json").read_text())
    assert state["research_status"] == "RUNNING_WITH_BLOCKERS"
    assert state["candidate_count"] == 1
    assert state["research_blockers"] == ["OOS_APPROVAL_MISSING"]
    assert state["last_order_ready_at"] is None
    assert state["execution_allowed"] is False


def test_virtual_market_daemon_prioritizes_and_acknowledges_manual_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.data import market_history_sync

    monkeypatch.setattr(
        market_history_sync, "read_cached_market_universe", lambda *_: None
    )
    settings = Settings(
        symbol="BTCUSDT",
        fixed_symbols=("HOTUSDT",),
        priority_watchlist=(),
        runtime_state_path=tmp_path / "runtime.json",
        runtime_cycle_interval_seconds=5,
    )
    request_path = tmp_path / "virtual-market-refresh-request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "VirtualMarketRefreshRequest/v1",
                "request_id": "dashboard:test",
                "requested_at": "2026-09-12T12:00:00+00:00",
                "market": "SPOT",
                "symbol": "HOTUSDT",
                "status": "PENDING",
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    seen: list[str] = []

    def research_cycle(
        settings: Settings,
        _acquisition: SnapshotAcquirer,
        *,
        cycle_report: dict[str, object] | None = None,
    ) -> int:
        assert cycle_report is not None
        seen.append(settings.symbol)
        cycle_report.update(
            snapshot_id="manual:HOTUSDT",
            candidate_count=2,
            research_blockers=("OOS_APPROVAL_MISSING",),
            virtual_decision_status="BLOCKED",
            virtual_order_ready=False,
        )
        return 0

    monkeypatch.setattr(
        runtime_cli, "_run_virtual_market_research_cycle", research_cycle
    )
    assert (
        runtime_cli.run_virtual_market_daemon(
            settings,
            max_cycles=1,
            public_acquisition=cast(SnapshotAcquirer, object()),
            clock=lambda: datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        )
        == 0
    )
    assert seen == ["HOTUSDT"]
    state = json.loads((tmp_path / "virtual-market.json").read_text())
    assert state["scan_lane"] == "MANUAL_REFRESH"
    acknowledgement = json.loads(request_path.read_text())
    assert acknowledgement["status"] == "COMPLETED"
    assert acknowledgement["candidate_count"] == 2
    assert acknowledgement["virtual_order_ready"] is False
    assert acknowledgement["blockers"] == ["OOS_APPROVAL_MISSING"]
    assert acknowledgement["execution_allowed"] is False


def test_virtual_market_manual_refresh_rejects_authority_drift_and_stale_request(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.json"
    payload = {
        "schema_version": "VirtualMarketRefreshRequest/v1",
        "request_id": "dashboard:test",
        "requested_at": "2026-09-12T12:00:00+00:00",
        "market": "SPOT",
        "symbol": "HOTUSDT",
        "status": "PENDING",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        runtime_cli._pending_virtual_market_refresh_request(
            request_path,
            ("HOTUSDT",),
            datetime(2026, 9, 12, 12, 11, tzinfo=UTC),
        )
        is None
    )
    payload["execution_allowed"] = True
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="REQUEST_INVALID"):
        runtime_cli._pending_virtual_market_refresh_request(
            request_path,
            ("HOTUSDT",),
            datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize("console_encoding", ["utf-8", "cp1252"])
def test_virtual_market_priority_revisits_preserve_discovery_and_restart_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    console_encoding: str,
) -> None:
    from io import BytesIO, TextIOWrapper

    from ai4binance.data import market_history_sync
    from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot

    output = BytesIO()
    stream = TextIOWrapper(output, encoding=console_encoding)
    monkeypatch.setattr(sys, "stdout", stream)
    universe = BinanceEligibleMarketSnapshot(
        spot_symbols=("AUSDT", "BTCUSDT", "ETHUSDT", "\u725b\u6765USDT"),
        futures_symbols=("BTCUSDT",),
        excluded_assets=(),
    )
    monkeypatch.setattr(
        market_history_sync, "read_cached_market_universe", lambda *_: universe
    )
    monkeypatch.setattr(
        runtime_cli,
        "_virtual_market_priority_symbols",
        lambda *_: ("BTCUSDT", "ETHUSDT"),
    )
    seen: list[str] = []

    def run(
        settings: Settings,
        source: SnapshotAcquirer,
        *,
        cycle_report: dict[str, object] | None = None,
    ) -> int:
        seen.append(settings.symbol)
        assert cycle_report is not None
        cycle_report.update(
            snapshot_id=settings.symbol, research_blockers=("OOS_DEPLOYMENT_MISSING",)
        )
        return 0

    monkeypatch.setattr(runtime_cli, "_run_virtual_market_research_cycle", run)
    settings = Settings(symbol="AUSDT", runtime_state_path=tmp_path / "runtime.json")
    sleeps: list[float] = []
    for count in (7, 3):
        assert (
            runtime_cli.run_virtual_market_daemon(
                settings,
                max_cycles=count,
                public_acquisition=cast(SnapshotAcquirer, object()),
                sleeper=sleeps.append,
            )
            == 0
        )
    assert seen == [
        "AUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "AUSDT",
        "BTCUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "AUSDT",
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert sleeps == [settings.virtual_market_cycle_interval_seconds] * 8
    state = json.loads((tmp_path / "virtual-market.json").read_text(encoding="utf-8"))
    assert state["scan_sequence"] == 10
    assert state["universe_symbol_count"] == 4
    assert state["supported_symbol_count"] == 3
    assert state["unsupported_symbols"] == ["\u725b\u6765USDT"]
    assert state["unsupported_symbol_reason"] == "PUBLIC_DATA_CLIENT_SYMBOL_UNSUPPORTED"
    assert state["scan_lane"] == "PRIORITY"
    assert state["last_order_ready_at"] is None
    projection = state["dashboard_simulation_projection"]
    assert projection["status"] == "COMPLETE"
    assert projection["eligible_symbol_count"] == 3
    assert projection["scanned_symbol_count"] == 3
    assert projection["pending_symbol_count"] == 0
    assert [row["symbol"] for row in projection["symbol_observations"]] == [
        "AUSDT",
        "BTCUSDT",
        "ETHUSDT",
    ]
    stream.flush()
    reports = [
        json.loads(line)
        for line in output.getvalue().decode(console_encoding).splitlines()
    ]
    assert reports[-1]["unsupported_symbols"] == state["unsupported_symbols"]
    assert all(report["cycle_exit_code"] == 0 for report in reports)


@pytest.mark.parametrize("primary_state", ["exception", "invalid", "valid"])
def test_virtual_market_local_acquisition_never_falls_back_to_public_rest(
    primary_state: str,
) -> None:
    from dataclasses import replace

    from tests.test_strategy_risk import snapshot

    primary_snapshot = replace(
        snapshot(),
        data_quality=DataQuality.DATA_VALID
        if primary_state == "valid"
        else DataQuality.DATA_INVALID,
    )

    class FailingAcquisition:
        @staticmethod
        def acquire(_symbol: str, _timeframes: tuple[str, ...]) -> MarketSnapshot:
            if primary_state == "exception":
                raise OSError("local snapshot unavailable")
            return primary_snapshot

    acquisition = runtime_cli._LocalFirstPublicAcquisition(
        primary=FailingAcquisition(),
    )

    if primary_state == "exception":
        with pytest.raises(OSError, match="local snapshot unavailable"):
            acquisition.acquire("HOTUSDT", ("1h",))
    else:
        assert acquisition.acquire("HOTUSDT", ("1h",)) is primary_snapshot


class _StubUrlopenResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_StubUrlopenResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._payload
        return self._payload[:size]


def _runtime_research_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Settings:
    root = tmp_path / "state" / "runtime_research"
    monkeypatch.setenv("AI4BINANCE_RUNTIME_NEWS_FEED_PATH", str(root / "news.jsonl"))
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_SOCIAL_FEED_PATH",
        str(root / "social.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_CONTENT_FEED_PATH",
        str(root / "content.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_TECHNOLOGY_FEED_PATH",
        str(root / "technology.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_CONTEXT_LEDGER_PATH",
        str(root / "evidence-ledger.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_OPPORTUNITY_REPORT_PATH",
        str(root / "opportunities-latest.json"),
    )
    return Settings()


def _read_jsonl_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        decoded = json.loads(line)
        assert isinstance(decoded, dict)
        rows.append(decoded)
    return rows


def test_runtime_feed_fetch_parses_rss_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rss_payload = """
    <rss>
      <channel>
        <item>
          <title>Listing launch approval</title>
          <link>https://www.coindesk.com/markets/hot-launch</link>
          <pubDate>Tue, 04 Aug 2026 20:20:00 GMT</pubDate>
        </item>
        <item>
          <title>Duplicate source</title>
          <link>https://www.coindesk.com/markets/hot-launch</link>
          <pubDate>Tue, 04 Aug 2026 20:21:00 GMT</pubDate>
        </item>
        <item>
          <title>Ignored insecure source</title>
          <link>http://www.coindesk.com/markets/not-allowed</link>
          <pubDate>Tue, 04 Aug 2026 20:22:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.strip().encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> _StubUrlopenResponse:
        del request, timeout
        return _StubUrlopenResponse(rss_payload)

    monkeypatch.setattr(runtime_cli, "urlopen", fake_urlopen)

    items = runtime_cli._fetch_feed_items(
        runtime_cli._NEWS_FEED_URL,
        max_items=3,
        max_file_bytes=4096,
    )

    assert len(items) == 1
    assert items[0].source_url == "https://www.coindesk.com/markets/hot-launch"


def test_runtime_feed_fetch_parses_atom_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    atom_payload = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Security launch update</title>
                <link
                    rel="alternate"
                    href="https://www.reddit.com/r/CryptoCurrency/comments/abc123/test/"
                />
        <updated>2026-08-04T20:25:00Z</updated>
      </entry>
      <entry>
        <title>Ignored insecure link</title>
        <link href="http://www.reddit.com/r/CryptoCurrency/comments/insecure" />
        <updated>2026-08-04T20:30:00Z</updated>
      </entry>
    </feed>
    """.strip().encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> _StubUrlopenResponse:
        del request, timeout
        return _StubUrlopenResponse(atom_payload)

    monkeypatch.setattr(runtime_cli, "urlopen", fake_urlopen)

    items = runtime_cli._fetch_feed_items(
        runtime_cli._SOCIAL_FEED_URL,
        max_items=3,
        max_file_bytes=4096,
    )

    assert len(items) == 1
    assert items[0].title == "Security launch update"
    assert items[0].source_url.startswith("https://www.reddit.com/")


def test_runtime_feed_fetch_with_blocker_returns_blocker_on_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_payload = b"<rss><channel><item><title>broken"

    def fake_urlopen(request: object, timeout: float) -> _StubUrlopenResponse:
        del request, timeout
        return _StubUrlopenResponse(invalid_payload)

    monkeypatch.setattr(runtime_cli, "urlopen", fake_urlopen)

    items, blocker = runtime_cli._fetch_feed_items_with_blocker(
        runtime_cli._NEWS_FEED_URL,
        max_items=3,
        max_file_bytes=4096,
        blocker="RUNTIME_NEWS_FEED_REFRESH_FAILED",
    )

    assert items == ()
    assert blocker == "RUNTIME_NEWS_FEED_REFRESH_FAILED"


def test_runtime_research_feed_refresh_writes_traceable_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _runtime_research_settings(monkeypatch, tmp_path)
    now = datetime(2026, 8, 4, 20, 40, tzinfo=UTC)
    news_items = (
        runtime_cli._WebFeedItem(
            title="Exchange launch approval",
            source_url="https://www.coindesk.com/markets/hot-launch",
            published_at=now,
        ),
    )
    social_items = (
        runtime_cli._WebFeedItem(
            title="Community partnership growth",
            source_url="https://www.reddit.com/r/CryptoCurrency/comments/abc123/test/",
            published_at=now,
        ),
    )
    technology_items = (
        runtime_cli._WebFeedItem(
            title="CodeQL security scanning launch",
            source_url="https://github.blog/changelog/2026-08-04-security-update/",
            published_at=now,
        ),
    )

    def fake_fetch(
        source_url: str,
        *,
        max_items: int,
        max_file_bytes: int,
        blocker: str,
    ) -> tuple[tuple[runtime_cli._WebFeedItem, ...], str | None]:
        del max_items, max_file_bytes, blocker
        if source_url == runtime_cli._NEWS_FEED_URL:
            return news_items, None
        if source_url == runtime_cli._SOCIAL_FEED_URL:
            return social_items, None
        if source_url == runtime_cli._TECHNOLOGY_FEED_URL:
            return technology_items, None
        raise AssertionError("unexpected feed URL")

    monkeypatch.setattr(runtime_cli, "_fetch_feed_items_with_blocker", fake_fetch)

    payload = runtime_cli._refresh_runtime_research_feeds(settings)

    assert payload["status"] == "READY"
    assert payload["counts"] == {
        "news": 1,
        "social": 1,
        "content": 1,
        "technology": 1,
    }
    user_report_paths = payload["user_report_paths"]
    assert isinstance(user_report_paths, dict)
    assert Path(user_report_paths["news"]["latest_json_path"]) == (
        tmp_path / "runtime" / "artifacts" / "user_reports" / "news" / "latest.json"
    )
    assert Path(user_report_paths["news"]["latest_markdown_path"]).is_file()
    assert Path(user_report_paths["technology"]["latest_json_path"]) == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "technology"
        / "latest.json"
    )
    assert Path(user_report_paths["technology"]["latest_markdown_path"]).is_file()

    news_rows = _read_jsonl_rows(settings.runtime_news_feed_path)
    social_rows = _read_jsonl_rows(settings.runtime_social_feed_path)
    content_rows = _read_jsonl_rows(settings.runtime_content_feed_path)
    technology_rows = _read_jsonl_rows(settings.runtime_technology_feed_path)

    assert news_rows[0]["source_url"] == "https://www.coindesk.com/markets/hot-launch"
    social_source = str(social_rows[0]["source_url"])
    assert social_source.startswith("https://www.reddit.com/")
    assert content_rows[0]["source"] == "coindesk-markets"
    assert technology_rows[0]["category"] == "application-security"


def test_runtime_news_row_attributes_only_eligible_coin_symbols() -> None:
    now = datetime(2026, 9, 11, tzinfo=UTC)
    row = runtime_cli._news_row(
        runtime_cli._WebFeedItem(
            title="Bitcoin market structure improves",
            source_url="https://www.coindesk.com/markets/bitcoin-structure",
            published_at=now,
        ),
        now,
        eligible_symbols=("BTCUSDT", "USDCUSDT", "WBTCUSDT", "BTCUPUSDT"),
    )

    assert row["symbol"] == "BTCUSDT"
    assert row["related_symbols"] == ["BTCUSDT"]

    macro = runtime_cli._news_row(
        runtime_cli._WebFeedItem(
            title="Core CPI rose faster in August",
            source_url="https://www.coindesk.com/markets/core-cpi",
            published_at=now,
        ),
        now,
        eligible_symbols=("AUSDT", "INUSDT", "ROSEUSDT"),
    )
    assert macro["symbol"] == "ALL"
    assert macro["related_symbols"] == []


def test_runtime_research_feed_refresh_returns_blocked_on_feed_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _runtime_research_settings(monkeypatch, tmp_path)
    now = datetime(2026, 8, 4, 20, 40, tzinfo=UTC)
    news_items = (
        runtime_cli._WebFeedItem(
            title="Exchange launch approval",
            source_url="https://www.coindesk.com/markets/hot-launch",
            published_at=now,
        ),
    )

    def fake_fetch(
        source_url: str,
        *,
        max_items: int,
        max_file_bytes: int,
        blocker: str,
    ) -> tuple[tuple[runtime_cli._WebFeedItem, ...], str | None]:
        del max_items, max_file_bytes, blocker
        if source_url == runtime_cli._NEWS_FEED_URL:
            return news_items, None
        if source_url == runtime_cli._SOCIAL_FEED_URL:
            return (), "RUNTIME_SOCIAL_FEED_REFRESH_FAILED"
        if source_url == runtime_cli._TECHNOLOGY_FEED_URL:
            return (), "RUNTIME_TECHNOLOGY_FEED_REFRESH_FAILED"
        raise AssertionError("unexpected feed URL")

    monkeypatch.setattr(runtime_cli, "_fetch_feed_items_with_blocker", fake_fetch)

    payload = runtime_cli._refresh_runtime_research_feeds(settings)

    assert payload["status"] == "BLOCKED"
    blockers = runtime_cli._text_sequence(payload.get("blockers"))
    assert "RUNTIME_SOCIAL_FEED_REFRESH_FAILED" in blockers
    assert "RUNTIME_TECHNOLOGY_FEED_REFRESH_FAILED" in blockers


def test_runtime_trace_validation_passes_with_matching_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _runtime_research_settings(monkeypatch, tmp_path)
    runtime_cli._write_jsonl_rows(
        settings.runtime_news_feed_path,
        [
            {
                "event_id": "news-1",
                "source_url": "https://www.coindesk.com/markets/hot-launch",
            }
        ],
    )
    runtime_cli._write_jsonl_rows(
        settings.runtime_technology_feed_path,
        [
            {
                "development_id": "tech-1",
                "source_url": "https://github.blog/changelog/2026-08-04-security-update/",
            }
        ],
    )
    opportunity_payload = {
        "snapshot_id": "binance:HOTUSDT:trace-pass",
        "opportunities": [
            {
                "opportunity_id": "op-1",
                "primary_source_url": "https://www.coindesk.com/markets/hot-launch",
                "trace_urls": [
                    "https://www.coindesk.com/markets/hot-launch",
                    "https://github.blog/changelog/2026-08-04-security-update/",
                ],
                "trace_evidence": [
                    {
                        "feed": "news",
                        "evidence_id": "news-1",
                        "source_url": "https://www.coindesk.com/markets/hot-launch",
                    },
                    {
                        "feed": "technology",
                        "evidence_id": "tech-1",
                        "source_url": "https://github.blog/changelog/2026-08-04-security-update/",
                    },
                ],
            }
        ],
    }
    settings.runtime_opportunity_report_path.parent.mkdir(parents=True, exist_ok=True)
    settings.runtime_opportunity_report_path.write_text(
        json.dumps(opportunity_payload, sort_keys=True),
        encoding="utf-8",
    )

    report, exit_code = runtime_cli._validate_runtime_research_traceability(settings)

    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["all_opportunities_traceable"] is True
    assert report["validated_count"] == 1
    assert Path(str(report["report_path"])).exists()


def test_runtime_trace_validation_blocks_when_report_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _runtime_research_settings(monkeypatch, tmp_path)

    report, exit_code = runtime_cli._validate_runtime_research_traceability(settings)

    assert exit_code == 2
    assert report["status"] == "BLOCKED"
    blockers = runtime_cli._text_sequence(report.get("blockers"))
    assert "RUNTIME_OPPORTUNITY_REPORT_UNAVAILABLE" in blockers


def test_runtime_trace_validation_blocks_on_mismatched_trace_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _runtime_research_settings(monkeypatch, tmp_path)
    runtime_cli._write_jsonl_rows(
        settings.runtime_news_feed_path,
        [
            {
                "event_id": "news-1",
                "source_url": "https://www.coindesk.com/markets/hot-launch",
            }
        ],
    )
    opportunity_payload = {
        "snapshot_id": "binance:HOTUSDT:trace-fail",
        "opportunities": [
            {
                "opportunity_id": "op-1",
                "primary_source_url": "https://www.coindesk.com/markets/hot-launch",
                "trace_urls": ["https://www.coindesk.com/markets/hot-launch"],
                "trace_evidence": [
                    {
                        "feed": "news",
                        "evidence_id": "news-missing",
                        "source_url": "https://www.coindesk.com/markets/hot-launch",
                    }
                ],
            }
        ],
    }
    settings.runtime_opportunity_report_path.parent.mkdir(parents=True, exist_ok=True)
    settings.runtime_opportunity_report_path.write_text(
        json.dumps(opportunity_payload, sort_keys=True),
        encoding="utf-8",
    )

    report, exit_code = runtime_cli._validate_runtime_research_traceability(settings)

    assert exit_code == 2
    assert report["status"] == "BLOCKED"
    assert report["mismatch_count"] == 1
    mismatches = report["mismatches"]
    assert isinstance(mismatches, tuple)
    assert len(mismatches) == 1
    errors = tuple(mismatches[0]["errors"])
    assert "TRACE_EVIDENCE_ID_NOT_FOUND:news:news-missing" in errors


def test_accounting_collect_once_fails_closed_without_credentials(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

    assert main(["accounting-collect-once"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["blockers"] == ["BINANCE_READ_ONLY_CREDENTIALS_UNAVAILABLE"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_accounting_status_reports_clean_current_files(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "accounting"
    required = (
        "spot/account_snapshots.jsonl",
        "spot/balance_snapshots.jsonl",
        "spot/cost_basis_positions.jsonl",
        "futures_usdm/account_snapshots.jsonl",
        "futures_usdm/asset_balances.jsonl",
        "futures_usdm/risk_snapshots.jsonl",
        "shared/api_sync_runs.jsonl",
        "shared/raw_api_events.jsonl",
        "shared/reconciliation_results.jsonl",
    )
    for relative in required:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "shared/reconciliation_results.jsonl":
            path.write_text(
                json.dumps({"payload": {"severity": "OK"}}) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(root))
    monkeypatch.setenv("AI4BINANCE_ACCOUNTING_FRESHNESS_MINUTES", "1440")

    assert main(["accounting-status"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "CLEAN"
    assert payload["reconciliation"]["status"] == "CLEAN"
    assert payload["execution_allowed"] is False


def test_accounting_status_reports_unreadable_file_without_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "accounting"
    for relative in (
        "shared/raw_api_events.jsonl",
        "shared/reconciliation_results.jsonl",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            {"payload": {"severity": "OK"}} if "reconciliation" in relative else {}
        )
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    spot_orders = root / "spot" / "orders.jsonl"
    spot_orders.parent.mkdir(parents=True)
    spot_orders.write_text("{}\n", encoding="utf-8")
    original_is_file = Path.is_file

    def guarded_is_file(path: Path) -> bool:
        if path == spot_orders:
            raise PermissionError("access denied")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", guarded_is_file)
    monkeypatch.setenv("AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(root))
    monkeypatch.setenv("AI4BINANCE_ACCOUNTING_FRESHNESS_MINUTES", "1440")

    assert main(["accounting-status"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DEGRADED"
    assert payload["blockers"] == ["ACCOUNTING_FILE_UNREADABLE:spot/orders.jsonl"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_accounting_daemon_reports_existing_instance_without_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "runtime.json"
    lock_path = state_path.with_name("accounting.lock")
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(str(os.getpid()), encoding="ascii")
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(state_path))

    assert main(["accounting-collect-daemon", "--max-cycles", "1"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["service"] == "accounting"
    assert payload["blockers"] == ["ACCOUNTING_DAEMON_ALREADY_ACTIVE"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_runtime_builds_private_services_from_allowlisted_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=file-key\nBINANCE_API_SECRET=file-secret\n",
        encoding="utf-8",
    )

    runtime = build_read_only_runtime(Settings())

    assert runtime.spot_wallet_service is not None
    assert runtime.futures_account_service is not None
    assert runtime.analytics_service is not None
    assert (
        runtime.analytics_service.prices.primary._transport.ticker_snapshot_filename
        == "wallet-price-coverage.json"
    )
    assert (
        runtime.analytics_service.prices.fallback._transport.ticker_snapshot_filename
        == "ticker-24hr.json"
    )
    assert runtime.research_service.memory_bridge is not None
    assert runtime.research_service.learning_loop.lifecycle_worker is not None
    assert runtime.research_service.audit_store.tamper_evident is True
    assert (
        runtime.research_service.audit_store.path.name
        == "runtime_research_events.chained.jsonl"
    )

"""CLI smoke tests."""

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.application import WhaleFusionCycle
from ai4binance.cli import build_read_only_runtime, main
from ai4binance.cli.commands import (
    COMMAND_SPECS,
    available_command_names,
    canonical_command,
    command_catalog_payload,
)
from ai4binance.cli.output import render_payload
from ai4binance.config import Settings
from ai4binance.exchange.errors import ExchangeTransportError
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle


def test_status_is_complete_and_safe_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "NO_TRADE"
    assert payload["decision_state"] == "NO_TRADE"
    assert payload["setup_tier"] == "NO_TRADE"
    assert payload["validation_status"] == "UNVALIDATED"
    assert payload["execution_allowed"] is False
    assert payload["trading_mode"] == "paper"
    assert payload["order_mode"] == "manual"
    assert payload["timeframes"] == ["15m", "1h", "4h", "1d"]
    assert payload["live_gate"]["status"] == "LIVE_ORDER_BLOCKED"
    assert "allow_auto_live_orders" in payload["live_gate"]["blockers"]
    assert "risk_penalty_score" in payload["sub_scores"]


def test_confirm_live_sets_only_one_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status", "--confirm-live"]) == 0
    payload = json.loads(capsys.readouterr().out)
    blockers = payload["live_gate"]["blockers"]
    assert "confirm_live" not in blockers
    assert "explicit_user_request" in blockers
    assert payload["live_gate"]["status"] == "LIVE_ORDER_BLOCKED"


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
    assert canonical_command("scan", "spot") == "scan-spot"
    assert canonical_command("scan", "futures") == "scan-futures"
    assert canonical_command("scan", "all") == "scan-all"
    assert canonical_command("scan", "margin") == "scan-unknown"


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


def test_summary_alias_and_text_output_remain_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["summary", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "Status:" in output
    assert "NO_TRADE" in output
    assert "LIVE_ORDER_BLOCKED" in output


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

    opportunities_text = render_payload(
        {
            "command": "opportunities",
            "inbox": {
                "symbol": "HOTUSDT",
                "blockers": ("NO_READY_CANDIDATE",),
                "items": (
                    {
                        "market": "SPOT",
                        "timeframe": "1h",
                        "setup_name": "trend_continuation",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                    },
                ),
            },
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        output_format="text",
        command="opportunities",
    )
    assert "visible_items: 1" in opportunities_text
    assert "trend_continuation" in opportunities_text

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
    assert payload["agent_count"] == 48
    assert payload["hard_gate_eligible_count"] == 0
    assert payload["live_eligible_count"] == 0
    assert payload["execution_allowed"] is False
    names = {agent["name"] for agent in payload["agents"]}
    assert {
        "trend",
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
    assert [stage["name"] for stage in payload["research_stages"]] == [
        "acquisition",
        "analysis",
        "strategy",
        "risk",
        "paper",
        "learning",
    ]
    audit_lines = (
        (tmp_path / "research_events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 1


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
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "btc.md").write_text(
        "BTCUSDT opportunity validation remains research only.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "AI4BINANCE_SECOND_BRAIN_INDEX_PATH",
        str(tmp_path / "State" / "second-brain-index.json"),
    )

    assert main(["second-brain", "--query", "BTCUSDT opportunity", "--ui"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["hits"][0]["source_uri"] == "Docs/btc.md"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert Path(payload["index_path"]).exists()
    assert Path(payload["ui_path"]).exists()


def test_lean_governance_cli_reports_operational_excellence_pillars(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
    (tmp_path / ".pytest-tmp").mkdir()

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
    assert "POKA_YOKE_CHECK_MISSING:QUALITY_GATE_GREEN" in payload["blockers"]


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
    assert "spot_wallet" not in payload
    assert "futures_account" not in payload
    assert payload["investment_management"]["recommendations"] == []
    assert payload["investment_management"]["execution_allowed"] is False
    assert state_path.exists()


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
    state_path = tmp_path / "State" / "runtime.json"
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
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "bnc.env").write_text(
        "BINANCE_API_KEY=file-key\nBINANCE_API_SECRET=file-secret\n",
        encoding="utf-8",
    )

    runtime = build_read_only_runtime(Settings())

    assert runtime.spot_wallet_service is not None
    assert runtime.futures_account_service is not None

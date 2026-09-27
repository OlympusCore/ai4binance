"""Parameter provenance and actual/counterfactual second-brain integration."""

import json
from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeClosureAssessment,
)
from ai4binance.intelligence.inventory import TradingIntelligenceInventory
from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.learning.storage import LearningStore
from ai4binance.rag import LocalRagIndexer
from ai4binance.research.backtesting import BacktestEngine, FuturesBacktestEngine
from ai4binance.research.backtesting.models import BacktestResult, TradeDirection
from tests.test_backtest_engine import NOW, candle, intent
from tests.test_futures_backtest_engine import (
    _candle,
    _dataset,
    _intent,
    _one_signal_provider,
)
from tests.test_trade_decision_evidence import evidence


def recorded_result(*, rejected: bool = False) -> BacktestResult:
    proposed = replace(
        intent(NOW),
        timestamp=NOW + timedelta(days=1) if rejected else NOW,
        decision_evidence=evidence(),
    )
    return BacktestEngine().run(
        symbol="BTCUSDT",
        timeframe="1h",
        candles=(
            candle(0, "100", "101", "99", "100"),
            candle(1, "100", "101", "94", "95"),
        ),
        signal_provider=lambda history: proposed if len(history) == 1 else None,
    )


@pytest.mark.parametrize("payload", [{"entry": None}, {"quantity": 3}, {"pnl": ""}])
def test_parameter_method_decoder_rejects_false_provenance(
    payload: dict[str, object],
) -> None:
    from ai4binance.domain.research.virtual_runtime_attribution import (
        TradeParameterMethods,
    )

    with pytest.raises(ValueError, match="strings"):
        TradeParameterMethods.from_payload(payload)


def test_spot_outcome_retains_values_and_parameter_sources() -> None:
    result = recorded_result()
    (outcome,) = result.trade_outcomes
    trade = result.trades[0]
    assert outcome.quantity == trade.quantity
    assert outcome.leverage is None
    assert outcome.initial_stop_loss == trade.initial_stop_loss
    assert outcome.initial_take_profit_levels == trade.initial_take_profit_levels
    assert outcome.planned_rr == trade.planned_rr
    assert outcome.net_pnl == trade.net_pnl_usdt
    assert outcome.decision_evidence == evidence()
    assert outcome.parameter_methods.leverage == "NOT_APPLICABLE_SPOT"
    assert "NOT_RECORDED" not in asdict(outcome.parameter_methods).values()


@pytest.mark.parametrize("exit_reason", ["TARGET", "HARD_STOP", "END_OF_DATA"])
def test_closure_distinguishes_observed_exit_from_method_accuracy(
    exit_reason: str,
) -> None:
    original = evidence()
    recorded = replace(
        original,
        factors_json=json.dumps(
            {
                "entry_zone": {"lower": "99", "upper": "101"},
                "state": {
                    "selected_scenario_id": "scenario-1",
                    "scenarios": [
                        {
                            "scenario_id": "scenario-1",
                            "evidence_for": ["observed-trigger"],
                            "evidence_against": ["observed-conflict"],
                        }
                    ],
                },
            }
        ),
    )
    assessment = TradeClosureAssessment.build(
        recorded,
        entry_time=NOW,
        entry_price=Decimal("100"),
        exit_reason=exit_reason,
    )
    assert assessment.decision_evidence_sha256 == recorded.sha256
    assert assessment.selected_scenario_id == "scenario-1"
    assert assessment.entry_quality == "FILL_WITHIN_RECORDED_ENTRY_ZONE"
    assert assessment.method_accuracy.startswith("NOT_EVALUABLE")
    assert assessment.scenario_accuracy.startswith("NOT_EVALUABLE")
    assert assessment.execution_quality.startswith("NOT_EVALUABLE")
    assert assessment.rule_evaluation_status.startswith("NOT_EVALUABLE")
    assert (assessment.target_quality == "TARGET_EXIT_RECORDED") is (
        exit_reason == "TARGET"
    )
    assert json.loads(recorded.factors_json)["state"]["scenarios"][0][
        "evidence_against"
    ] == ["observed-conflict"]


@pytest.mark.parametrize("kind", ["missing", "future", "reconstructed"])
def test_closure_cannot_upgrade_noncausal_or_reconstructed_evidence(kind: str) -> None:
    from ai4binance.domain.research.virtual_runtime_attribution import (
        TradeDecisionEvidence,
    )

    recorded = replace(
        evidence(), factors_json='{"entry_zone":{"lower":"99","upper":"101"}}'
    )
    if kind == "missing":
        recorded = TradeDecisionEvidence()
    elif kind == "future":
        recorded = replace(recorded, as_of=NOW + timedelta(seconds=1))
    else:
        recorded = replace(recorded, status="RECONSTRUCTED_FROM_ARCHIVE")
    assessment = TradeClosureAssessment.build(
        recorded, entry_time=NOW, entry_price=Decimal("100"), exit_reason="TARGET"
    )
    assert assessment.decision_lineage_status.startswith("NOT_EVALUABLE")
    assert assessment.entry_quality.startswith("NOT_EVALUABLE")
    assert assessment.selected_scenario_id is None


def test_learning_retains_observed_closure_diagnostics_without_promotion() -> None:
    result = recorded_result()
    outcome = replace(
        result.trade_outcomes[0],
        decision_evidence=replace(
            evidence(), factors_json='{"entry_zone":{"lower":"90","upper":"91"}}'
        ),
    )
    summary = ControlledLearningEngine().analyze(
        created_at=NOW, trade_outcomes=(outcome,)
    )
    payload = json.loads(summary.evidence_cases[0].payload_json)
    assessment = payload["closure_assessment"]
    assert assessment["entry_quality"] == "FILL_OUTSIDE_RECORDED_ENTRY_ZONE"
    assert "ENTRY_FILL_OUTSIDE_RECORDED_ZONE" in summary.evidence_cases[0].tags
    assert assessment["decision_evidence_sha256"] == outcome.decision_evidence.sha256
    assert not summary.execution_allowed
    assert not summary.risk_change_allowed


@pytest.mark.parametrize("direction", tuple(TradeDirection))
def test_futures_records_directional_geometry_and_leverage(
    direction: TradeDirection,
) -> None:
    rows = (_candle(0), _candle(1), _candle(2))
    proposed = replace(
        _intent(
            rows[0].timestamp,
            direction,
            stop_loss="90" if direction is TradeDirection.LONG else "110",
            take_profit="120" if direction is TradeDirection.LONG else "80",
        ),
        decision_evidence=evidence(),
    )
    engine = FuturesBacktestEngine()
    result = engine.run(
        dataset=_dataset(rows), signal_provider=_one_signal_provider(proposed)
    )
    (outcome,) = result.trade_outcomes
    assert outcome.direction is direction
    assert outcome.leverage == engine.config.leverage
    assert outcome.quantity is not None
    assert outcome.quantity > 0
    assert outcome.initial_stop_loss == proposed.stop_loss
    assert outcome.initial_take_profit_levels == (proposed.take_profit,)
    assert outcome.planned_rr is not None
    assert outcome.planned_rr > 0
    assert "NOT_RECORDED" not in asdict(outcome.parameter_methods).values()


def test_learning_cases_are_retrievable_and_do_not_merge_counterfactual_pnl(
    tmp_path: Path,
) -> None:
    actual = recorded_result()
    missed = recorded_result(rejected=True)
    store = LearningStore(
        tmp_path / "runtime/state/learning_summary.json",
        tmp_path / "runtime/state/learning_audit.jsonl",
    )
    loop = ControlledLearningLoop(store, ControlledLearningEngine())
    first = loop.run(created_at=NOW, backtests=(actual, missed))
    assert first.saved
    cases = first.summary.evidence_cases
    assert {case.kind for case in cases} == {"CLOSED_TRADE", "MISSED_OPPORTUNITY"}
    assert len(cases) == 2
    assert sum(case.kind == "CLOSED_TRADE" for case in cases) == len(actual.trades)
    assert not first.summary.execution_allowed
    assert not first.summary.risk_change_allowed
    loss = next(
        item for item in first.summary.lessons if item.code == "CLOSED_TRADE_LOSS"
    )
    assert len(loss.evidence_refs) == 1
    index = LocalRagIndexer(tmp_path).build(now=NOW)
    hits = index.query("CONFIRMED_SWING_GRAPH CLOSE_RECLAIM")
    assert hits
    assert all("learning_cases/" in hit.source_uri for hit in hits)
    assert not index.execution_allowed
    second = loop.run(created_at=NOW, backtests=(actual, missed))
    assert not second.saved
    assert (
        len(tuple((store.summary_path.parent / "learning_cases").glob("*.json"))) == 2
    )
    changed = replace(
        actual, trades=(replace(actual.trades[0], trade_id="different-trade"),)
    )
    third = loop.run(created_at=NOW, backtests=(changed, missed))
    assert third.saved
    assert third.summary.summary_id != first.summary.summary_id


def test_idempotent_learning_rejects_tampered_case(tmp_path: Path) -> None:
    store = LearningStore(tmp_path / "summary.json", tmp_path / "audit.jsonl")
    loop = ControlledLearningLoop(store, ControlledLearningEngine())
    result = recorded_result()
    loop.run(created_at=NOW, backtests=(result,))
    case = next((tmp_path / "learning_cases").glob("*.json"))
    case.write_text('{"fabricated": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="content mismatch"):
        loop.run(created_at=NOW, backtests=(result,))


def test_large_decision_factors_cannot_hide_parameter_values_from_rag(
    tmp_path: Path,
) -> None:
    recorded = replace(
        evidence(),
        factors_json=json.dumps({"closed_candles": [{"close": "100"}] * 500}),
    )
    result = recorded_result()
    trade = replace(
        result.trades[0],
        attribution=replace(result.trades[0].attribution, decision_evidence=recorded),
    )
    result = replace(result, trades=(trade,))
    store = LearningStore(
        tmp_path / "runtime/state/learning_summary.json",
        tmp_path / "runtime/state/learning_audit.jsonl",
    )
    loop = ControlledLearningLoop(store, ControlledLearningEngine())
    loop.run(created_at=NOW, backtests=(result,))
    index = LocalRagIndexer(tmp_path).build(now=NOW)
    for query in ("quantity", "stop_loss", "net_pnl", "CONFIRMED_SWING_GRAPH"):
        assert index.query(query), query
    path = next((store.summary_path.parent / "learning_cases").glob("*.json"))
    payload = json.loads(path.read_text())
    assert (
        payload["payload"]["decision_evidence"]["factors_json"] == recorded.factors_json
    )
    payload.pop("analysis_summary")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not loop.run(created_at=NOW, backtests=(result,)).saved
    assert "analysis_summary" in json.loads(path.read_text())


def test_missing_forward_data_never_becomes_a_profit_case(tmp_path: Path) -> None:
    engine = BacktestEngine()
    record = engine._insufficient_evidence_record(
        replace(intent(NOW), decision_evidence=evidence()),
        ("INSUFFICIENT_FORWARD_DATA",),
        "pre-veto:test",
    )
    assert record.proposed_quantity == engine.config.quantity
    assert record.proposed_entry is None
    assert record.proposed_rr is None
    assert record.forward_net_pnl is None
    assert record.forward_trade_outcome is None
    assert "NOT_RECORDED" not in asdict(record.parameter_methods).values()
    summary = (
        ControlledLearningLoop(
            LearningStore(tmp_path / "summary.json", tmp_path / "audit.jsonl"),
            ControlledLearningEngine(),
        )
        .run(created_at=NOW, missed_opportunities=(record,))
        .summary
    )
    assert any(item.code == "MISSED_INSUFFICIENT_EVIDENCE" for item in summary.lessons)
    assert json.loads(summary.evidence_cases[0].payload_json)["forward_net_pnl"] is None


def test_replay_closure_enters_learning_with_complete_parameter_provenance(
    tmp_path: Path,
) -> None:
    from tests.test_historical_replay_runner import (
        END,
        START,
        _OpenOnceOrchestrator,
        _request,
        _runner,
        _snapshot,
    )

    store = LearningStore(tmp_path / "summary.json", tmp_path / "audit.jsonl")
    result = _runner(
        orchestrator=_OpenOnceOrchestrator(),
    ).run(
        _request(),
        (
            _snapshot(START, snapshot_id="methods-open"),
            _snapshot(
                END, snapshot_id="methods-close", high="120", low="60", close="72"
            ),
        ),
    )
    assert result.closed_trades
    from ai4binance.historical_replay_evaluation import HistoricalReplaySystemEvaluator

    # Replay deliberately excludes mutable learning. Ingest only after completion.
    HistoricalReplaySystemEvaluator().evaluate(
        result,
        learning_loop=ControlledLearningLoop(store, ControlledLearningEngine()),
    )
    cases = [
        json.loads(path.read_text())
        for path in (tmp_path / "learning_cases").glob("*.json")
    ]
    closed = [case["payload"] for case in cases if case["kind"] == "CLOSED_TRADE"]
    assert len(closed) == 1
    assert Decimal(closed[0]["quantity"]) == result.closed_trades[0].quantity
    assert closed[0]["planned_rr"] is not None
    assert "NOT_RECORDED" not in closed[0]["parameter_methods"].values()


def test_inventory_exposes_missing_variants_and_cannot_claim_method_oos() -> None:
    inventory = TradingIntelligenceInventory()
    inventory.validate()
    rows = {row.family: row for row in inventory.methods}
    assert len(rows) == 11
    assert rows["harmonic_patterns"].implemented == ("gartley", "bat")
    assert "butterfly" in rows["harmonic_patterns"].missing
    assert "zigzag" in rows["elliott_waves"].missing
    assert "flag" in rows["chart_patterns"].missing
    assert all(
        row.performance_status == "METHOD_LEVEL_OOS_NOT_VERIFIED"
        for row in rows.values()
    )
    root = Path(__file__).resolve().parents[1]
    assert all((root / test).is_file() for row in rows.values() for test in row.tests)
    with pytest.raises(ValueError, match="incomplete"):
        replace(inventory, methods=inventory.methods[:-1]).validate()


def test_paper_order_lifecycle_restart_and_learning_keep_methods(
    tmp_path: Path,
) -> None:
    from ai4binance.execution.ledger import PaperLedger
    from ai4binance.execution.lifecycle import PaperLifecycleEngine, StagedExitPlan
    from ai4binance.execution.paper import PaperBroker
    from tests.test_paper_execution import approved_assessment, approved_candidate
    from tests.test_paper_lifecycle import candle as paper_candle

    candidate = replace(approved_candidate(), decision_evidence=evidence())
    order = PaperBroker().submit(candidate, approved_assessment(), candidate.timestamp)
    engine = PaperLifecycleEngine()
    position = engine.open_position(
        order,
        stop_loss=candidate.stop_loss,
        atr=candidate.atr,
        plan=StagedExitPlan(candidate.take_profit_levels, (Decimal("1"),)),
    )
    closed = engine.process_candle(
        position,
        replace(
            paper_candle(1, "100", "101", "94", "95"),
            timestamp=candidate.timestamp + timedelta(hours=1),
        ),
    )
    ledger = PaperLedger(tmp_path / "paper.jsonl")
    ledger.append(
        closed, event_type="PAPER_POSITION_CLOSED", timestamp=closed.exits[-1].timestamp
    )
    restored = ledger.latest_position(closed.position_id)
    assert restored == closed
    assert restored is not None
    assert restored.decision_evidence == evidence()
    assert restored.planned_rr == order.planned_rr
    assert "NOT_RECORDED" not in asdict(restored.parameter_methods).values()
    summary = (
        ControlledLearningLoop(
            LearningStore(tmp_path / "summary.json", tmp_path / "audit.jsonl"),
            ControlledLearningEngine(),
        )
        .run(
            created_at=closed.exits[-1].timestamp,
            paper_positions=ledger.closed_positions(),
        )
        .summary
    )
    assert summary.evidence_cases[0].kind == "PAPER_POSITION"
    assert json.loads(summary.evidence_cases[0].payload_json)[
        "realized_pnl_usdt"
    ] == str(closed.realized_pnl_usdt)


def test_second_brain_cli_allows_persisted_learning_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance.cli.research import run_second_brain
    from ai4binance.config import Settings

    store = LearningStore(
        tmp_path / "runtime/state/learning_summary.json",
        tmp_path / "runtime/state/learning_audit.jsonl",
    )
    ControlledLearningLoop(store, ControlledLearningEngine()).run(
        created_at=NOW, backtests=(recorded_result(),)
    )
    monkeypatch.chdir(tmp_path)
    status = run_second_brain(
        Settings(),
        query="CONFIRMED_SWING_GRAPH CLOSE_RECLAIM",
        subject=None,
        use_llm=False,
        render_ui=False,
    )
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert any("learning_cases/" in hit["source_uri"] for hit in payload["hits"])
    assert payload["execution_allowed"] is False

"""Read-only wallet and controlled-learning boundary tests."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.application.learning_loop import (
    ControlledLearningLoop,
    PaperLedgerLearningEvidenceProvider,
)
from ai4binance.domain import ValidationStatus
from ai4binance.execution.ledger import PaperLedger
from ai4binance.execution.lifecycle import (
    LifecyclePosition,
    PaperClosureReview,
    PositionStatus,
    StagedExitPlan,
)
from ai4binance.execution.paper import ExitReason
from ai4binance.learning import ControlledLearningEngine, LearningStore
from ai4binance.learning.models import LearningSummary
from ai4binance.portfolio import WalletSnapshotService
from ai4binance.storage import DestinationVerificationError, JsonlAuditStore
from tests.test_cli import public_snapshot

NOW = datetime(2026, 4, 1, tzinfo=UTC)


class StubAccountReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "10", "locked": "2"},
                {"asset": "USDT", "free": "100", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return [
            {
                "orderId": 1,
                "clientOrderId": "spot-1",
                "symbol": symbol,
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "0.001",
                "origQty": "100",
                "executedQty": "0",
            }
        ]


def test_wallet_service_normalizes_read_only_account_snapshot() -> None:
    snapshot = WalletSnapshotService(StubAccountReader()).capture("hotusdt", NOW)

    assert snapshot.symbol == "HOTUSDT"
    assert snapshot.account_status == "SPOT"
    assert snapshot.can_trade is True
    assert snapshot.open_order_count == 1
    assert snapshot.open_orders[0].client_order_id == "spot-1"
    hot_balance = snapshot.balance("hot")
    assert hot_balance is not None
    assert hot_balance.free == Decimal("10")
    assert not hasattr(StubAccountReader(), "create_order")


class InvalidAccountReader:
    def account(self) -> object:
        return {"accountType": "SPOT", "canTrade": True, "balances": "invalid"}

    def open_orders(self, symbol: str | None = None) -> object:
        return []


def test_wallet_service_rejects_invalid_private_payload() -> None:
    with pytest.raises(ValueError, match="balances must be an array"):
        WalletSnapshotService(InvalidAccountReader()).capture("HOTUSDT", NOW)


def closed_position() -> LifecyclePosition:
    review = PaperClosureReview(
        exit_reason=ExitReason.TRAILING_STOP_EXIT,
        lifecycle_error=None,
        stop_quality="PROTECTIVE",
        trailing_quality="PROTECTIVE",
        ignored_signals=1,
        htf_weakness=True,
        volatility_expansion=False,
        level_break=True,
        staged_exit_alternative="NOT_USED_REVIEW",
        lesson_candidate="REVIEW_PREMATURE_TRAILING",
    )
    return LifecyclePosition(
        position_id="paper:1",
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.1"),
        initial_quantity=Decimal("1"),
        remaining_quantity=Decimal("0"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("102"),
        atr=Decimal("2"),
        plan=StagedExitPlan((Decimal("110"),), (Decimal("1"),)),
        status=PositionStatus.CLOSED,
        closure_review=review,
    )


def test_learning_ranks_lessons_without_execution_or_risk_authority() -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(), closed_position()),
    )

    assert summary.lessons[0].code == "REVIEW_PREMATURE_TRAILING"
    assert summary.lessons[0].evidence_count == 2
    assert summary.experiments[0].rank == 1
    assert summary.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert summary.execution_allowed is False
    assert summary.risk_change_allowed is False
    assert summary.application_state == "NOT_APPLIED"
    assert summary.promotion_evidence_required is True
    assert summary.closure_evidence_required is True


def test_learning_store_writes_atomic_summary_and_append_only_audit(
    tmp_path: Path,
) -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(),),
    )
    store = LearningStore(
        tmp_path / "learning_summary.json",
        tmp_path / "learning_events.jsonl",
    )
    store.save(summary)

    persisted = json.loads(store.summary_path.read_text(encoding="utf-8"))
    audit = json.loads(store.audit_path.read_text(encoding="utf-8"))
    assert persisted["summary_id"] == summary.summary_id
    assert audit["event_type"] == "LEARNING_SUMMARY_CREATED"
    assert audit["snapshot_id"] == summary.summary_id
    assert audit["tamper_evident"] is True
    assert audit["previous_record_sha256"] == "GENESIS"
    assert (
        JsonlAuditStore(store.audit_path, tamper_evident=True).verify_chain()
        == (audit["record_sha256"])
    )


def test_paper_ledger_learning_provider_loads_closed_positions(
    tmp_path: Path,
) -> None:
    ledger = PaperLedger(tmp_path / "paper-ledger.jsonl")
    position = closed_position()
    ledger.append(position, event_type="PAPER_POSITION_CLOSED", timestamp=NOW)

    evidence = PaperLedgerLearningEvidenceProvider(ledger).load(public_snapshot())

    assert evidence == {"paper_positions": (position,)}


def test_paper_ledger_learning_provider_accepts_closed_position_protocol() -> None:
    position = closed_position()

    class _ProtocolLedger:
        def closed_positions(self) -> tuple[object, ...]:
            return (position,)

    evidence = PaperLedgerLearningEvidenceProvider(_ProtocolLedger()).load(
        public_snapshot()
    )

    assert evidence == {"paper_positions": (position,)}


def test_learning_store_stops_when_summary_read_back_is_tampered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(),),
    )
    store = LearningStore(
        tmp_path / "learning_summary.json",
        tmp_path / "learning_events.jsonl",
    )
    original = Path.read_text

    def tampered_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        payload = original(self, encoding, errors)
        return (
            payload.replace(summary.summary_id, "other-summary")
            if self == store.summary_path
            else payload
        )

    monkeypatch.setattr(Path, "read_text", tampered_read_text)
    with pytest.raises(DestinationVerificationError, match="LEARNING_SUMMARY"):
        store.save(summary)


def test_empty_learning_evidence_is_deterministic() -> None:
    first = ControlledLearningEngine().analyze(created_at=NOW)
    second = ControlledLearningEngine().analyze(created_at=NOW)

    assert first == second
    assert first.lessons == ()
    assert first.experiments == ()


def test_unchanged_learning_is_reanalyzed_and_refreshed_when_stale(
    tmp_path: Path,
) -> None:
    store = LearningStore(tmp_path / "summary.json", tmp_path / "events.jsonl")
    loop = ControlledLearningLoop(store, ControlledLearningEngine())
    first = loop.run(created_at=NOW, paper_positions=(closed_position(),))
    repeated = loop.run(
        created_at=NOW + timedelta(hours=23), paper_positions=(closed_position(),)
    )
    assert repeated.saved is False
    assert len(store.audit_path.read_text().splitlines()) == 1
    refreshed_at = NOW + timedelta(days=1)
    refreshed = loop.run(created_at=refreshed_at, paper_positions=(closed_position(),))
    assert refreshed.saved is True
    assert refreshed.summary.summary_id == first.summary.summary_id
    payload = json.loads(store.summary_path.read_text())
    assert payload["created_at"] == refreshed_at.isoformat()
    assert payload["execution_allowed"] is False
    assert payload["risk_change_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert len(store.audit_path.read_text().splitlines()) == 2
    assert JsonlAuditStore(store.audit_path, tamper_evident=True).verify_chain()


def test_failed_learning_analysis_does_not_refresh_stale_summary(
    tmp_path: Path,
) -> None:
    store = LearningStore(tmp_path / "summary.json", tmp_path / "events.jsonl")
    loop = ControlledLearningLoop(store, ControlledLearningEngine())
    loop.run(created_at=NOW)
    previous = store.summary_path.read_bytes(), store.audit_path.read_bytes()
    with pytest.raises(AttributeError):
        loop.run(created_at=NOW + timedelta(days=2), paper_positions=(object(),))
    assert (store.summary_path.read_bytes(), store.audit_path.read_bytes()) == previous


def test_learning_aggregates_backtest_walkforward_and_tuning_evidence() -> None:
    backtests = (
        SimpleNamespace(
            rejected_signals=("r1", "r2"),
            metrics=SimpleNamespace(trade_count=3),
            missed_opportunity_ledger=SimpleNamespace(
                records=(
                    SimpleNamespace(
                        counterfactual_result="BAD_BLOCK",
                        blockers=("THRESHOLD_MISS",),
                    ),
                )
            ),
        ),
        SimpleNamespace(
            rejected_signals=("r3",),
            metrics=SimpleNamespace(trade_count=9),
            missed_opportunity_ledger=SimpleNamespace(records=()),
        ),
    )
    walk_forward_reports = (
        SimpleNamespace(blockers=("LOW_OOS_TRADE_COUNT", "LOW_OOS_TRADE_COUNT")),
    )
    tuning_reports = (SimpleNamespace(blockers=("PARAMETER_INSTABILITY",)),)
    typed_backtests = cast(tuple[Any, ...], backtests)
    typed_walk_forward = cast(tuple[Any, ...], walk_forward_reports)
    typed_tuning_reports = cast(tuple[Any, ...], tuning_reports)

    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        backtests=typed_backtests,
        walk_forward_reports=typed_walk_forward,
        tuning_reports=typed_tuning_reports,
        paper_positions=(closed_position(),),
    )

    by_code = {lesson.code: lesson for lesson in summary.lessons}
    assert by_code["REJECTED_SIGNALS"].evidence_count == 3
    assert by_code["MISSED_BAD_BLOCK"].evidence_count == 1
    assert by_code["IMPROVEMENT_CANDIDATE"].evidence_count == 1
    assert by_code["BAD_BLOCK_THRESHOLD_MISS"].evidence_count == 1
    assert by_code["OOS_LOW_OOS_TRADE_COUNT"].evidence_count == 2
    assert by_code["LOW_TRADE_COUNT"].evidence_count == 1
    assert by_code["TUNING_PARAMETER_INSTABILITY"].evidence_count == 1
    assert by_code["REVIEW_PREMATURE_TRAILING"].evidence_count == 1
    assert all(exp.rank >= 1 for exp in summary.experiments)
    assert summary.experiments[0].experiment_id.startswith("experiment:")


def test_learning_consumes_performance_improvement_candidates_report_only() -> None:
    performance_snapshots = cast(
        tuple[Any, ...],
        (
            SimpleNamespace(
                auto_learn_consumable=True,
                root_cause_tags=("ENTRY_GATING_REVIEW",),
                improvement_candidates=(
                    SimpleNamespace(
                        affected_component="DGE",
                        sample_size=7,
                    ),
                ),
            ),
        ),
    )

    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        performance_snapshots=performance_snapshots,
    )

    by_code = {lesson.code: lesson for lesson in summary.lessons}
    assert by_code["PERFORMANCE_IMPROVEMENT_DGE"].evidence_count == 7
    assert by_code["ROOT_CAUSE_ENTRY_GATING_REVIEW"].evidence_count == 1
    assert summary.experiments[0].experiment_id == (
        "experiment:performance_improvement_dge"
    )
    assert summary.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert summary.execution_allowed is False
    assert summary.risk_change_allowed is False


def test_learning_builds_profitability_optimization_loop_from_trade_evidence() -> None:
    losing_trade = SimpleNamespace(
        net_pnl_usdt=Decimal("-10"),
        gross_pnl_usdt=Decimal("-8"),
        fee_cost_usdt=Decimal("1"),
        slippage_cost_usdt=Decimal("1"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("-1"),
        maximum_favorable_excursion=Decimal("24"),
        maximum_adverse_excursion=Decimal("12"),
        attribution=SimpleNamespace(
            strategy_id="trend_continuation",
            strategy_version="1",
            regime="TREND",
        ),
    )
    winning_trade = SimpleNamespace(
        net_pnl_usdt=Decimal("20"),
        gross_pnl_usdt=Decimal("22"),
        fee_cost_usdt=Decimal("1"),
        slippage_cost_usdt=Decimal("1"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("2"),
        maximum_favorable_excursion=Decimal("22"),
        maximum_adverse_excursion=Decimal("5"),
        attribution=SimpleNamespace(
            strategy_id="trend_continuation",
            strategy_version="1",
            regime="TREND",
        ),
    )
    backtests = cast(
        tuple[Any, ...],
        (
            SimpleNamespace(
                trades=(losing_trade, winning_trade),
                rejected_signals=("block-1", "block-2"),
                metrics=SimpleNamespace(
                    trade_count=2,
                    max_drawdown=0.12,
                    net_return=0.1,
                    expectancy_usdt=5.0,
                    profit_factor=2.0,
                    win_rate=0.5,
                ),
                equity_curve=(
                    SimpleNamespace(
                        timestamp=datetime(2026, 4, 1, tzinfo=UTC),
                        equity_usdt=Decimal("1000"),
                    ),
                    SimpleNamespace(
                        timestamp=datetime(2026, 4, 2, tzinfo=UTC),
                        equity_usdt=Decimal("1020"),
                    ),
                    SimpleNamespace(
                        timestamp=datetime(2026, 4, 3, tzinfo=UTC),
                        equity_usdt=Decimal("1010"),
                    ),
                ),
                funnel_telemetry=SimpleNamespace(
                    stage_counts=(
                        ("DISCOVERED", 4),
                        ("READY_FOR_RISK", 3),
                        ("RISK_PASS", 3),
                        ("VALIDATION_PASS", 2),
                        ("DGE_PASS", 2),
                        ("VIRTUAL_ORDER", 2),
                        ("FILLED", 2),
                        ("CLOSED", 2),
                    )
                ),
            ),
        ),
    )
    walk_forward_reports = cast(
        tuple[Any, ...],
        (
            SimpleNamespace(
                folds=(
                    SimpleNamespace(
                        oos_result=SimpleNamespace(
                            trades=(winning_trade,),
                            metrics=SimpleNamespace(
                                net_return=0.03,
                                max_drawdown=0.04,
                            ),
                        )
                    ),
                    SimpleNamespace(
                        oos_result=SimpleNamespace(
                            trades=(losing_trade,),
                            metrics=SimpleNamespace(
                                net_return=-0.01,
                                max_drawdown=0.06,
                            ),
                        )
                    ),
                )
            ),
        ),
    )

    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        backtests=backtests,
        walk_forward_reports=walk_forward_reports,
    )

    loop = summary.profitability_loop
    assert loop is not None
    assert loop.stages[0] == "ClosedTrades"
    assert loop.stages[-1] == "PaperCandidate"
    metrics = {item.metric_id: item for item in loop.metrics}
    assert metrics["net_expectancy_after_costs"].value == pytest.approx(5.0)
    assert metrics["oos_expectancy"].value == pytest.approx(5.0)
    assert metrics["candidate_to_execution_conversion"].value == pytest.approx(0.5)
    assert metrics["profitable_walk_forward_window_ratio"].value == pytest.approx(0.5)
    assert metrics["blocker_opportunity_cost"].value == pytest.approx(10.0)
    assert loop.strategy_regime_attribution[0].strategy_id == "trend_continuation"
    assert loop.failure_analyses[0].classification == "EXIT_MANAGEMENT_GIVEBACK"
    assert loop.failure_analyses[0].average_mfe_r == pytest.approx(2.4)
    assert loop.failure_analyses[0].average_mae_r == pytest.approx(1.2)
    assert loop.experiments[0].required_validation == (
        "bounded_experiment",
        "walk_forward",
        "oos",
        "cost_stress",
        "human_review",
        "paper_candidate",
    )
    assert loop.experiment_candidates == ()
    assert summary.execution_allowed is False
    assert summary.risk_change_allowed is False


def test_learning_proposes_regime_disable_experiment_candidate_report_only() -> None:
    trend_winner = SimpleNamespace(
        net_pnl_usdt=Decimal("12"),
        gross_pnl_usdt=Decimal("13"),
        fee_cost_usdt=Decimal("0.5"),
        slippage_cost_usdt=Decimal("0.5"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("1.2"),
        maximum_favorable_excursion=Decimal("15"),
        maximum_adverse_excursion=Decimal("4"),
        attribution=SimpleNamespace(
            strategy_id="strategy_a",
            strategy_version="1",
            regime="TREND_UP",
        ),
    )
    trend_winner_2 = SimpleNamespace(
        net_pnl_usdt=Decimal("18"),
        gross_pnl_usdt=Decimal("19"),
        fee_cost_usdt=Decimal("0.5"),
        slippage_cost_usdt=Decimal("0.5"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("1.8"),
        maximum_favorable_excursion=Decimal("20"),
        maximum_adverse_excursion=Decimal("5"),
        attribution=SimpleNamespace(
            strategy_id="strategy_a",
            strategy_version="1",
            regime="TREND_UP",
        ),
    )
    range_loser = SimpleNamespace(
        net_pnl_usdt=Decimal("-8"),
        gross_pnl_usdt=Decimal("-7"),
        fee_cost_usdt=Decimal("0.5"),
        slippage_cost_usdt=Decimal("0.5"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("-0.8"),
        maximum_favorable_excursion=Decimal("6"),
        maximum_adverse_excursion=Decimal("9"),
        attribution=SimpleNamespace(
            strategy_id="strategy_a",
            strategy_version="1",
            regime="RANGE",
        ),
    )
    range_loser_2 = SimpleNamespace(
        net_pnl_usdt=Decimal("-10"),
        gross_pnl_usdt=Decimal("-9"),
        fee_cost_usdt=Decimal("0.5"),
        slippage_cost_usdt=Decimal("0.5"),
        funding_cost_usdt=Decimal("0"),
        realized_r_multiple=Decimal("-1.2"),
        maximum_favorable_excursion=Decimal("7"),
        maximum_adverse_excursion=Decimal("11"),
        attribution=SimpleNamespace(
            strategy_id="strategy_a",
            strategy_version="1",
            regime="RANGE",
        ),
    )
    backtests = cast(
        tuple[Any, ...],
        (
            SimpleNamespace(
                trades=(
                    trend_winner,
                    trend_winner_2,
                    range_loser,
                    range_loser_2,
                ),
                rejected_signals=(),
                metrics=SimpleNamespace(
                    trade_count=4,
                    max_drawdown=0.08,
                    net_return=0.04,
                    expectancy_usdt=3.0,
                    profit_factor=1.5,
                    win_rate=0.5,
                ),
                equity_curve=(),
                funnel_telemetry=SimpleNamespace(
                    stage_counts=(
                        ("DISCOVERED", 4),
                        ("FILLED", 4),
                    )
                ),
            ),
        ),
    )

    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        backtests=backtests,
    )

    loop = summary.profitability_loop
    assert loop is not None
    assert len(loop.experiment_candidates) == 1
    candidate = loop.experiment_candidates[0]
    assert candidate.status == "EXPERIMENT_CANDIDATE"
    assert candidate.strategy_id == "strategy_a"
    assert candidate.regime == "RANGE"
    assert candidate.sample_size == 2
    assert candidate.baseline_expectancy_r == pytest.approx(-1.0)
    assert candidate.reference_regime == "TREND_UP"
    assert candidate.reference_expectancy_r == pytest.approx(1.5)
    assert candidate.workflow == (
        "Baseline",
        "Candidate",
        "Replay",
        "WalkForward",
        "OOS",
        "Compare",
        "HumanReview",
        "Promotion",
    )
    assert candidate.recommendation == (
        "Disable strategy_a in RANGE until replay, walk-forward and OOS evidence "
        "improve expectancy."
    )
    assert candidate.human_review_required is True
    assert candidate.execution_allowed is False
    assert candidate.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert summary.execution_allowed is False
    assert summary.risk_change_allowed is False


def test_learning_profitability_loop_is_absent_without_profitability_evidence() -> None:
    summary = ControlledLearningEngine().analyze(created_at=NOW)

    assert summary.profitability_loop is None


def test_learning_ignores_zero_evidence_entries() -> None:
    backtests = cast(
        tuple[Any, ...],
        (
            SimpleNamespace(
                rejected_signals=(),
                metrics=SimpleNamespace(trade_count=7),
            ),
        ),
    )

    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        backtests=backtests,
    )

    assert summary.lessons == ()
    assert summary.experiments == ()


def test_learning_summary_model_rejects_authority_drift() -> None:
    with pytest.raises(ValueError, match="identity"):
        LearningSummary("", NOW, (), ())
    with pytest.raises(ValueError, match="timezone-aware"):
        LearningSummary("summary-1", datetime(2026, 4, 1), (), ())
    with pytest.raises(ValueError, match="research only"):
        LearningSummary(
            "summary-1",
            NOW,
            (),
            (),
            promotion_status=ValidationStatus.PAPER_APPROVED,
        )
    with pytest.raises(ValueError, match="execute or change risk"):
        LearningSummary("summary-1", NOW, (), (), execution_allowed=True)
    with pytest.raises(ValueError, match="execute or change risk"):
        LearningSummary("summary-1", NOW, (), (), risk_change_allowed=True)
    with pytest.raises(ValueError, match="applied improvements"):
        LearningSummary("summary-1", NOW, (), (), application_state="APPLIED")
    with pytest.raises(ValueError, match="promotion and closure evidence"):
        LearningSummary(
            "summary-1",
            NOW,
            (),
            (),
            promotion_evidence_required=False,
        )

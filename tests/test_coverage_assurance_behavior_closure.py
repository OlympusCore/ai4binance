"""Behavioral closure proofs for architecture-sensitive coverage targets."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

import ai4binance.governance.dge_engine as dge_engine
import ai4binance.historical_replay_state as replay_state
from ai4binance.governance.adapters import DgeEvaluationRecord
from ai4binance.governance.audit import persist_dge_evaluation_record
from ai4binance.governance.controls import ControlSeverity
from ai4binance.governance.dge_models import (
    DgeDecisionStatus,
    DgeMarketAction,
    DgeRuleSeverity,
)
from ai4binance.governance.execution_authority import ExecutionAutomationMode
from ai4binance.governance.replay import replay_dge_decision
from ai4binance.opportunity_outcomes import (
    MissedOpportunityAssessment,
    MissedOpportunityCause,
    OpportunityOutcomeClass,
    OpportunityOutcomeEvaluation,
    OpportunityOutcomeStatus,
    classify_missed_opportunity,
    evaluate_opportunity_outcome,
)
from ai4binance.reporting import to_primitive
from ai4binance.research import VirtualMarket
from ai4binance.research.backtesting import (
    FuturesBacktestConfig,
    FuturesBacktestEngine,
    FuturesBacktestIntent,
)
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    MissedOpportunityCategory,
    TradeDirection,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage import JsonlAuditStore
from ai4binance.validation import RuntimeFuturesReplayDataset
from tests.test_dge_models import dge_candidate, dge_context, governed_decision
from tests.test_futures_backtest_engine import START as FUTURES_START
from tests.test_futures_backtest_engine import _candle as futures_candle
from tests.test_futures_backtest_engine import _dataset as futures_dataset
from tests.test_futures_backtest_engine import _intent as futures_intent
from tests.test_historical_replay_runner import (
    END,
    START,
    _dual_market_request,
    _NoCandidateOrchestrator,
    _request,
    _runner,
    _snapshot,
)


def test_trade_decision_serialization_denial_is_semantic() -> None:
    decision = governed_decision(
        governed_action=DgeMarketAction.NO_TRADE,
        governance_status=DgeDecisionStatus.NO_TRADE,
        simulated_execution_allowed=False,
        paper_execution_allowed=False,
        reason_summary="hard blocker denied the candidate",
    )

    payload = json.loads(json.dumps(to_primitive(decision), sort_keys=True))

    assert payload["governed_action"] == "NO_TRADE"
    assert payload["execution_allowed"] is False
    assert payload["live_execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_dge_decision_authority_mismatches_fail_closed() -> None:
    decision = governed_decision(
        simulated_execution_allowed=False,
        paper_execution_allowed=True,
    )
    assert decision.virtual_simulation_allowed is False
    assert decision.auto_simulation_allowed is False
    assert decision.binance_order_allowed is False
    assert decision.live_order_allowed is False

    with pytest.raises(ValueError, match="paper execution compatibility"):
        replace(
            decision,
            simulated_execution_allowed=True,
            paper_execution_allowed=False,
        )
    with pytest.raises(ValueError, match="auto simulation requires"):
        replace(
            decision,
            auto_execution_allowed=True,
            simulated_execution_allowed=False,
        )
    with pytest.raises(ValueError, match="authority profile"):
        replace(decision, authority_profile_id="wrong-profile")
    with pytest.raises(ValueError, match="automation mode"):
        replace(
            decision,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
        )
    with pytest.raises(ValueError, match="autonomous simulation"):
        replace(
            decision,
            simulated_execution_allowed=True,
            auto_execution_allowed=True,
        )
    with pytest.raises(ValueError, match="simulated execution"):
        replace(decision, simulated_execution_allowed=True)
    with pytest.raises(ValueError, match="autonomous learning"):
        replace(decision, autonomous_learning_allowed=True)
    with pytest.raises(ValueError, match="self-improvement"):
        replace(decision, bounded_self_improvement_allowed=True)
    with pytest.raises(ValueError, match="simulated Spot"):
        replace(decision, simulated_spot_allowed=True)
    with pytest.raises(ValueError, match="simulated Futures"):
        replace(decision, simulated_futures_allowed=True)
    with pytest.raises(ValueError, match="manual confirmation"):
        replace(decision, requires_manual_confirmation=False)


def test_dge_helper_fallbacks_preserve_conservative_semantics() -> None:
    assert (
        dge_engine._reason_summary(DgeDecisionStatus.WATCH_ONLY, (), (), object())
        == "DGE returned a conservative non-executable decision."
    )
    assert dge_engine._control_severity(DgeRuleSeverity.WARNING) is (
        ControlSeverity.WARNING
    )
    assert dge_engine._control_severity(DgeRuleSeverity.SOFT) is ControlSeverity.MEDIUM
    assert dge_engine._soft_penalty_value(DgeRuleSeverity.WARNING) == Decimal("3")


def test_dge_replay_existing_ledger_missing_decision_fails_closed(
    tmp_path: Path,
) -> None:
    record = DgeEvaluationRecord(
        source="coverage_assurance_event_replay",
        candidate=dge_candidate(),
        context=dge_context(),
        decision=governed_decision(simulated_execution_allowed=False),
    )
    persisted = persist_dge_evaluation_record(tmp_path, record)

    assert persisted.replay_result is not None
    replay = replay_dge_decision(tmp_path, "dge:unrelated")

    assert replay.status == "NON_REPRODUCIBLE"
    assert replay.checked_fields == ()
    assert replay.blocker == "DGE_REPLAY_RECORD_NOT_FOUND"
    assert replay.execution_allowed is False
    assert replay.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_historical_replay_restored_state_rejects_semantic_drift(
    tmp_path: Path,
) -> None:
    request = _request()
    result = _runner().run(
        request,
        (_snapshot(START, snapshot_id="coverage-assurance-restored-state"),),
    )
    store = replay_state.HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    assert store.persist(result) is True
    restored = store.restore(request)
    assert restored is not None

    invalid_cases = (
        ({"run_id": "../escape"}, "run id"),
        ({"request_seed_sha256": "invalid"}, "request seed hash"),
        ({"previous_state_sha256": "invalid"}, "previous state hash"),
        ({"last_sequence": -1}, "sequence cannot be negative"),
        ({"cycle_semantic_sha256s": ()}, "cycle hash chain"),
        ({"final_portfolios": ()}, "market-independent"),
        ({"equity_curves": restored.equity_curves * 2}, "equity markets"),
        ({"blockers": (" ",)}, "blockers must be unique"),
        ({"execution_allowed": True}, "cannot authorize trading"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(restored, **changes)


def test_historical_replay_reset_contract_rejects_invalid_lifecycle(
    tmp_path: Path,
) -> None:
    request = _dual_market_request()
    result = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        request,
        (
            _snapshot(
                START,
                snapshot_id="coverage-reset-spot",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="coverage-reset-futures",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
        ),
    )
    store = replay_state.HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    assert store.persist(result) is True
    capitals = (
        replay_state.HistoricalReplayResetCapital(VirtualMarket.SPOT, Decimal("500")),
        replay_state.HistoricalReplayResetCapital(
            VirtualMarket.USD_M_FUTURES, Decimal("500")
        ),
    )
    reset = store.reset_wallet_epochs(
        result,
        reset_at=END + timedelta(minutes=1),
        capitals=capitals,
        confirmation=replay_state.VIRTUAL_WALLET_RESET_CONFIRMATION,
    )

    invalid_cases = (
        ({"reset_id": " "}, "identity"),
        ({"status": "UNKNOWN"}, "status is invalid"),
        ({"previous_result_semantic_sha256": "invalid"}, "result hash"),
        ({"blockers": ("blocked",)}, "must be unblocked"),
        ({"new_epochs": reset.new_epochs[:1]}, "requires both markets"),
        (
            {
                "previous_epochs": (
                    reset.new_epochs[0],
                    reset.previous_epochs[1],
                )
            },
            "lifecycle is inconsistent",
        ),
        (
            {"status": "RESET_BLOCKED", "blockers": (), "persisted": False},
            "requires blockers and no write",
        ),
        ({"execution_allowed": True}, "cannot authorize trading"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(reset, **changes)


def test_historical_replay_store_and_payload_parsers_fail_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="tail limit"):
        replay_state.HistoricalReplayStateStore(tmp_path / "state.jsonl", 0)

    request = _request()
    result = _runner().run(
        request,
        (_snapshot(START, snapshot_id="coverage-assurance-parser"),),
    )
    store = replay_state.HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    assert store.persist(result) is True
    restored = store.restore(request)
    assert restored is not None

    with pytest.raises(ValueError, match="cannot precede replay"):
        store.reset_wallet_epochs(
            result,
            reset_at=START - timedelta(seconds=1),
            capitals=(),
            confirmation=replay_state.VIRTUAL_WALLET_RESET_CONFIRMATION,
        )
    with pytest.raises(ValueError, match="STATE_NOT_PERSISTED"):
        replay_state.HistoricalReplayStateStore.for_run(
            tmp_path / "missing", request.run_id
        ).reset_wallet_epochs(
            result,
            reset_at=END,
            capitals=(),
            confirmation=replay_state.VIRTUAL_WALLET_RESET_CONFIRMATION,
        )
    with pytest.raises(ValueError, match="one capital per market"):
        store.reset_wallet_epochs(
            result,
            reset_at=END,
            capitals=(
                replay_state.HistoricalReplayResetCapital(
                    VirtualMarket.SPOT, Decimal("100")
                ),
            ),
            confirmation=replay_state.VIRTUAL_WALLET_RESET_CONFIRMATION,
        )
    dual_request = _dual_market_request()
    dual_result = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        dual_request,
        (
            _snapshot(
                START,
                snapshot_id="coverage-parser-spot",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="coverage-parser-futures",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
        ),
    )
    dual_store = replay_state.HistoricalReplayStateStore.for_run(
        tmp_path / "dual", dual_request.run_id
    )
    assert dual_store.persist(dual_result) is True
    dual_restored = dual_store.restore(dual_request)
    assert dual_restored is not None
    with pytest.raises(ValueError, match="MARKET_SCOPE_MISMATCH"):
        replay_state.HistoricalReplayStateStore._validate_request_binding(
            dual_request,
            replace(
                dual_restored,
                final_portfolios=dual_restored.final_portfolios[:1],
            ),
        )
    drifted_portfolio = replace(
        restored.final_portfolios[0], portfolio_id="portfolio:drifted"
    )
    with pytest.raises(ValueError, match="EPOCH_MISMATCH"):
        replay_state.HistoricalReplayStateStore._validate_request_binding(
            request,
            replace(
                restored,
                final_portfolios=(drifted_portfolio, *restored.final_portfolios[1:]),
            ),
        )
    with pytest.raises(ValueError, match="schema is unsupported"):
        replay_state._state_from_payload({"schema_version": "unsupported"})

    parser_cases = (
        (lambda: replay_state._mapping([], "record"), "must be an object"),
        (lambda: replay_state._sequence({}, "items"), "must be an array"),
        (lambda: replay_state._text_item(" ", "text"), "is invalid"),
        (lambda: replay_state._decimal_value(object(), "decimal"), "is invalid"),
        (lambda: replay_state._decimal_value("NaN", "decimal"), "is invalid"),
        (lambda: replay_state._integer_value(True, "integer"), "is invalid"),
        (
            lambda: replay_state._timestamp({"timestamp": "not-a-time"}, "timestamp"),
            "timestamp is invalid",
        ),
        (lambda: replay_state._boolean({}, "flag"), "must be boolean"),
        (
            lambda: replay_state._require_utc("timestamp", datetime(2026, 9, 11)),
            "timezone-aware UTC",
        ),
    )
    for operation, message in parser_cases:
        with pytest.raises(ValueError, match=message):
            operation()


def test_historical_replay_restore_rejects_event_and_state_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    result = _runner().run(
        request,
        (_snapshot(START, snapshot_id="coverage-assurance-tamper"),),
    )
    store = replay_state.HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    assert store.persist(result) is True
    record = json.loads(store.path.read_text(encoding="utf-8"))

    def skip_chain_verification(_store: object) -> None:
        return None

    monkeypatch.setattr(
        JsonlAuditStore,
        "verify_chain",
        skip_chain_verification,
    )
    record["event_type"] = "UNRELATED_EVENT"
    store.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="PERSISTED_EVENT_INVALID"):
        store.restore(request)

    record["event_type"] = "HISTORICAL_REPLAY_WALLET_CHECKPOINT"
    record["payload"]["state_sha256"] = "0" * 64
    store.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="STATE_HASH_MISMATCH"):
        store.restore(request)


def _outcome(
    *,
    direction: str = "BULLISH",
    high: str = "103",
    low: str = "99",
    invalidation: str | None = "97",
    target: str | None = "102",
) -> OpportunityOutcomeEvaluation:
    observed_at = datetime(2026, 9, 11, 10, tzinfo=UTC)
    candle = OHLCVCandle(
        timestamp=observed_at,
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal("100"),
        volume=Decimal("10"),
    )
    return evaluate_opportunity_outcome(
        opportunity_id="opportunity:coverage-assurance",
        direction=direction,
        reference_price=Decimal("100"),
        observed_at=observed_at,
        future_candles=(candle,),
        evaluation_horizon=1,
        dataset_id="dataset:coverage-assurance",
        timeframe="1h",
        invalidation_price=None if invalidation is None else Decimal(invalidation),
        target_price=None if target is None else Decimal(target),
    )


def test_opportunity_outcome_contracts_reject_invalid_or_authorizing_state() -> None:
    outcome = _outcome()
    assert outcome.final_outcome_class is OpportunityOutcomeClass.TARGET_FIRST

    invalid_cases = (
        ({"outcome_id": " "}, "identity is required"),
        ({"evaluation_started_at": datetime(2026, 9, 11)}, "timezone-aware"),
        ({"evaluation_horizon": 0}, "horizon and price"),
        ({"outcome_reason_codes": ("A", "A")}, "reasons must be unique"),
        ({"outcome_reason_codes": (" ",)}, "reasons cannot be blank"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"maximum_favorable_excursion": None}, "is incomplete"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(outcome, **changes)


def test_opportunity_outcome_classes_and_counterfactual_isolation() -> None:
    invalidated = _outcome(high="101", low="96", target="105")
    favorable = _outcome(high="104", low="99", invalidation=None, target=None)
    adverse = _outcome(high="101", low="95", invalidation=None, target=None)
    mixed = _outcome(high="102", low="98", invalidation=None, target=None)

    assert invalidated.final_outcome_class is OpportunityOutcomeClass.INVALIDATED_FIRST
    assert favorable.final_outcome_class is OpportunityOutcomeClass.FAVORABLE
    assert adverse.final_outcome_class is OpportunityOutcomeClass.ADVERSE
    assert mixed.final_outcome_class is OpportunityOutcomeClass.MIXED
    assert all(
        item.execution_allowed is False for item in (invalidated, favorable, adverse)
    )

    pending = replace(
        favorable,
        status=OpportunityOutcomeStatus.PENDING_HORIZON,
        evaluation_completed_at=None,
        maximum_favorable_excursion=None,
        maximum_adverse_excursion=None,
        time_to_mfe_bars=None,
        time_to_mae_bars=None,
    )
    window_end = favorable.evaluation_completed_at
    assert window_end is not None
    review = classify_missed_opportunity(
        opportunity_id="opportunity:coverage-assurance",
        symbol="BTCUSDT",
        market="SPOT",
        timeframe="1h",
        window_start=favorable.evaluation_started_at,
        window_end=window_end,
        counterfactual_detection_time=favorable.evaluation_started_at,
        actual_detection_time=None,
        cause=MissedOpportunityCause.RUNTIME_FAILURE,
        outcome=pending,
    )
    assert review.assessment is MissedOpportunityAssessment.UNRESOLVED
    assert review.lookahead_safe_reconstruction_status == "NOT_EVALUABLE"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="direction is invalid"):
        _outcome(direction="SIDEWAYS")
    with pytest.raises(ValueError, match="timeframe is unsupported"):
        evaluate_opportunity_outcome(
            opportunity_id="opportunity:invalid-timeframe",
            direction="BULLISH",
            reference_price=Decimal("100"),
            observed_at=favorable.evaluation_started_at,
            future_candles=(),
            evaluation_horizon=1,
            dataset_id="dataset:coverage-assurance",
            timeframe="7m",
        )
    with pytest.raises(ValueError, match="inputs are invalid"):
        evaluate_opportunity_outcome(
            opportunity_id="opportunity:invalid-input",
            direction="BULLISH",
            reference_price=Decimal("0"),
            observed_at=favorable.evaluation_started_at,
            future_candles=(),
            evaluation_horizon=1,
            dataset_id="dataset:coverage-assurance",
            timeframe="1h",
        )


def test_missed_opportunity_review_rejects_semantic_drift() -> None:
    outcome = _outcome(high="101", low="96", target="105")
    assert outcome.evaluation_completed_at is not None
    review = classify_missed_opportunity(
        opportunity_id="opportunity:review",
        symbol="BTCUSDT",
        market="SPOT",
        timeframe="1h",
        window_start=outcome.evaluation_started_at,
        window_end=outcome.evaluation_completed_at,
        counterfactual_detection_time=outcome.evaluation_started_at,
        actual_detection_time=outcome.evaluation_started_at,
        cause=MissedOpportunityCause.RISK_BLOCKED,
        outcome=outcome,
    )
    assert review.assessment is MissedOpportunityAssessment.CORRECT_BLOCK

    invalid_cases = (
        ({"symbol": " "}, "identity is required"),
        ({"actual_detection_time": datetime(2026, 9, 11)}, "timezone-aware"),
        (
            {"opportunity_window_end": review.opportunity_window_start - timedelta(1)},
            "window is invalid",
        ),
        (
            {
                "lookahead_safe_reconstruction_status": "NOT_EVALUABLE",
                "assessment": MissedOpportunityAssessment.CORRECT_BLOCK,
            },
            "must remain unresolved",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(review, **changes)


def test_futures_contracts_and_veto_boundaries_fail_closed() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        FuturesBacktestConfig(maintenance_margin_ratio=Decimal("NaN"))
    with pytest.raises(ValueError, match="must be positive"):
        FuturesBacktestConfig(maintenance_margin_ratio=Decimal("0"))

    intent = futures_intent(
        FUTURES_START,
        TradeDirection.LONG,
        stop_loss="90",
        take_profit="110",
    )
    intent_cases = (
        ({"signal_id": " "}, "identity is required"),
        ({"timestamp": datetime(2026, 9, 11)}, "timezone-aware"),
        ({"direction": "LONG"}, "direction must be"),
        ({"stop_loss": Decimal("0")}, "prices must be"),
        ({"reason_codes": ()}, "reason codes are required"),
        ({"reason_codes": ("A", "A")}, "reason codes must be unique"),
        ({"maximum_holding_bars": 0}, "holding_bars must be positive"),
        ({"strategy_id": " "}, "strategy_id is required"),
        ({"entry_score": Decimal("-1")}, "scores must be"),
        ({"blocker_history": ("A", "A")}, "blocker history"),
        ({"funnel_stages": ()}, "funnel stages are invalid"),
    )
    for changes, message in intent_cases:
        with pytest.raises(ValueError, match=message):
            replace(intent, **changes)

    candles = (futures_candle(0), futures_candle(1), futures_candle(2))
    dataset = futures_dataset(candles)
    engine = FuturesBacktestEngine()

    def unsupported_signal_provider(
        _replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent:
        return cast(FuturesBacktestIntent, object())

    with pytest.raises(TypeError, match="RuntimeFuturesReplayDataset"):
        engine._validate_dataset(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="unsupported intent"):
        engine.run(dataset=dataset, signal_provider=unsupported_signal_provider)

    normalized = engine._normalize_intent(
        replace(intent, symbol="", snapshot_id="", decision_id=""), dataset
    )
    assert normalized.symbol == dataset.symbol
    assert normalized.snapshot_id == dataset.dataset_sha256
    assert normalized.decision_id == f"decision:{intent.signal_id}"
    blockers = engine._intent_blockers(
        replace(normalized, timestamp=candles[1].timestamp, timeframe="15m"),
        candles[0].timestamp,
        engine._open_trade(normalized, candles[1]),
        {normalized.signal_id},
        dataset,
    )
    assert blockers == (
        "SIGNAL_TIMESTAMP_MISMATCH",
        "SIGNAL_TIMEFRAME_MISMATCH",
        "DUPLICATE_SIGNAL_ID",
        "POSITION_ALREADY_OPEN",
    )


def test_futures_entry_exit_and_counterfactual_edges_are_explicit() -> None:
    long_intent = futures_intent(
        FUTURES_START,
        TradeDirection.LONG,
        stop_loss="101",
        take_profit="99",
    )
    short_intent = futures_intent(
        FUTURES_START,
        TradeDirection.SHORT,
        stop_loss="99",
        take_profit="101",
    )
    candle = futures_candle(1)
    engine = FuturesBacktestEngine(
        FuturesBacktestConfig(minimum_notional=Decimal("1000000"))
    )
    long_blockers = engine._entry_blockers(long_intent, candle, Decimal("0"))
    short_blockers = engine._entry_blockers(short_intent, candle, Decimal("0"))
    assert "FUTURES_LONG_GEOMETRY_INVALID" in long_blockers
    assert "FUTURES_SHORT_GEOMETRY_INVALID" in short_blockers
    assert "INSUFFICIENT_BACKTEST_MARGIN" in long_blockers
    assert "MIN_NOTIONAL_NOT_REACHED" in long_blockers

    zero_fill = FuturesBacktestEngine(
        FuturesBacktestConfig(quantity=Decimal("0.00001"), step_size=Decimal("0.001"))
    )._entry_fill(candle.volume)
    assert zero_fill.filled_quantity == Decimal("0")
    assert zero_fill.blockers == ("STEP_SIZE_ROUNDED_QUANTITY_IS_ZERO",)

    valid_engine = FuturesBacktestEngine()
    open_trade = valid_engine._open_trade(
        futures_intent(
            FUTURES_START,
            TradeDirection.LONG,
            stop_loss="90",
            take_profit="120",
        ),
        candle,
    )
    stop = valid_engine._exit_decision(
        open_trade,
        futures_candle(2, high="110", low="89", close="95"),
    )
    assert stop is not None
    assert stop.reason is BacktestExitReason.HARD_STOP

    timed_trade = replace(
        open_trade,
        intent=replace(open_trade.intent, maximum_holding_bars=1),
        bars_held=1,
    )
    timed = valid_engine._exit_decision(
        timed_trade,
        futures_candle(2, high="105", low="95", close="101"),
    )
    assert timed is not None
    assert timed.reason is BacktestExitReason.TIME_EXIT

    neutral_trade = replace(
        valid_engine._close_trade(
            open_trade,
            futures_candle(2).timestamp,
            stop,
        ),
        realized_r_multiple=Decimal("0"),
    )
    assert valid_engine._counterfactual_category(neutral_trade) is (
        MissedOpportunityCategory.NEUTRAL_BLOCK
    )


def test_futures_dataset_and_end_of_replay_boundaries_are_explicit() -> None:
    engine = FuturesBacktestEngine()
    one_candle_dataset = futures_dataset(
        (futures_candle(0),),
        funding=((0, "0.001"),),
    )
    with pytest.raises(ValueError, match="at least two closed"):
        engine._validate_dataset(one_candle_dataset)

    dataset = futures_dataset((futures_candle(0), futures_candle(1), futures_candle(2)))
    object.__setattr__(dataset, "market", "SPOT")
    with pytest.raises(ValueError, match="identity is unsupported"):
        engine._validate_dataset(dataset)
    object.__setattr__(dataset, "market", "USD_M_FUTURES")

    base_intent = futures_intent(
        FUTURES_START,
        TradeDirection.LONG,
        stop_loss="80",
        take_profit="130",
    )

    def duplicate_while_open(
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        candles = replay.candles
        if len(candles) <= 2:
            return replace(base_intent, timestamp=candles[-1].timestamp)
        return None

    end_of_data = engine.run(
        dataset=dataset,
        signal_provider=duplicate_while_open,
    )
    assert end_of_data.trades[0].exit_reason is BacktestExitReason.END_OF_DATA
    assert "DUPLICATE_SIGNAL_ID" in end_of_data.rejected_signals[0].blockers
    assert "POSITION_ALREADY_OPEN" in end_of_data.rejected_signals[0].blockers

    def last_candle_only(
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        candles = replay.candles
        if len(candles) == len(dataset.candles):
            return replace(base_intent, timestamp=candles[-1].timestamp)
        return None

    no_next_bar = engine.run(dataset=dataset, signal_provider=last_candle_only)
    assert no_next_bar.trades == ()
    assert no_next_bar.rejected_signals[0].blockers == ("NO_NEXT_BAR",)
    assert (
        no_next_bar.missed_opportunity_ledger.records[0].forward_trade_outcome is None
    )

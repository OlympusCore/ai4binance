"""Regression tests for conservative event-driven Spot backtesting."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.application.governance.memory_approval import (
    MemoryApprovalVerificationService,
    MemoryPromotionRequest,
)
from ai4binance.core.contracts.memory import (
    MemoryAuthorityCeiling,
    MemoryCandidate,
    MemoryProducerRole,
    MemoryPromotionApprovalRecord,
    MemoryPromotionVerificationRecord,
    MemoryPromotionVerificationResult,
    MemoryRetrievalRequest,
    MemoryTrustClass,
    MemoryType,
    MemoryWriteIntent,
)
from ai4binance.domain.memory import GovernedMemoryFabric
from ai4binance.research.backtesting import (
    BacktestConfig,
    BacktestEngine,
    BacktestIntent,
)
from ai4binance.research.backtesting import engine as backtest_engine
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    MissedOpportunityCategory,
)
from ai4binance.research.backtesting.storage import BacktestAuditWriter
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage.jsonl import JsonlAuditStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)
HASH = "b" * 64


def test_backtest_intent_derives_opportunity_lineage() -> None:
    intent = BacktestIntent(
        signal_id="signal:lineage",
        timestamp=NOW,
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        atr=Decimal("2"),
    )

    assert intent.opportunity_id == "opportunity:signal:lineage"
    assert intent.closed_trade_attribution.opportunity_id == intent.opportunity_id


def test_counterfactual_tail_view_preserves_suffix_without_copying() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "101", "102", "100", "101"),
        candle(2, "102", "103", "101", "102"),
    )

    tail = backtest_engine._CandleTail(candles, 1)

    assert tuple(tail) == candles[1:]
    assert tail[0] is candles[1]
    assert tail[-1] is candles[-1]
    assert tail[::-1] == tuple(reversed(candles[1:]))
    with pytest.raises(IndexError, match="tail index"):
        _ = tail[2]


@pytest.mark.parametrize(
    ("future", "take_profit", "maximum_holding_bars"),
    [
        (("100", "101", "94", "95"), Decimal("110"), None),
        (("100", "111", "99", "110"), Decimal("110"), None),
        (
            (
                ("100", "104", "99", "103"),
                ("103", "104", "99", "101"),
            ),
            Decimal("130"),
            None,
        ),
        (
            (
                ("100", "102", "99", "101"),
                ("101", "103", "100.5", "102"),
            ),
            Decimal("130"),
            1,
        ),
        (
            (
                ("100", "102", "99", "101"),
                ("101", "103", "100.5", "102"),
            ),
            Decimal("130"),
            None,
        ),
    ],
)
def test_single_target_counterfactual_fast_path_matches_general_engine(
    future: tuple[str, str, str, str] | tuple[tuple[str, str, str, str], ...],
    take_profit: Decimal,
    maximum_holding_bars: int | None,
) -> None:
    rows = future if isinstance(future[0], tuple) else (future,)
    replay = tuple(candle(index, *row) for index, row in enumerate(rows))
    proposed = replace(
        intent(NOW),
        take_profit=take_profit,
        maximum_holding_bars=maximum_holding_bars,
    )
    engine = BacktestEngine()

    fast = engine._simulate_single_target_counterfactual(
        engine._open_trade(proposed, replay[0]),
        replay,
    )
    general = engine._simulate_counterfactual_trade_general(
        engine._open_trade(proposed, replay[0]),
        replay,
    )

    assert fast == general


def candle(
    offset: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=NOW + timedelta(hours=offset),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def intent(timestamp: datetime, signal_id: str = "signal-1") -> BacktestIntent:
    return BacktestIntent(
        signal_id=signal_id,
        timestamp=timestamp,
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        atr=Decimal("2"),
        entry_score=Decimal("82"),
        evidence_score=Decimal("71"),
        dge_status="DGE_PASS",
    )


def memory_intent(intent_id: str, observed_at: datetime) -> MemoryWriteIntent:
    return MemoryWriteIntent(
        intent_id=intent_id,
        memory_type=MemoryType.SEMANTIC_MEMORY,
        subject_key="strategy:backtest_replay",
        body="Backtest replay memory must respect the simulated clock.",
        event_time=NOW,
        observed_at=observed_at,
        source_refs=("runtime/artifacts/backtest/replay.json",),
        evidence_refs=("backtest:memory-aware-replay",),
        source_hashes=(HASH,),
        producer_role=MemoryProducerRole.OBSERVER,
        trust_class=MemoryTrustClass.VERIFIED_SYSTEM_EVIDENCE,
        authority_ceiling=MemoryAuthorityCeiling.ADVISORY,
        confidence=0.80,
    )


def memory_promotion_verification(
    candidate: MemoryCandidate,
    approval_record_id: str,
    verification_record_id: str,
) -> MemoryPromotionVerificationResult:
    approval = MemoryPromotionApprovalRecord(
        approval_record_id=approval_record_id,
        candidate_memory_id=candidate.record.memory_id,
        candidate_content_hash=candidate.record.content_hash,
        approver_ref="governance-reviewer",
        approved_at=NOW + timedelta(seconds=10),
        policy_version="governed-memory-fabric:v1",
    )
    verification = MemoryPromotionVerificationRecord(
        verification_record_id=verification_record_id,
        approval_record_id=approval_record_id,
        candidate_memory_id=candidate.record.memory_id,
        candidate_content_hash=candidate.record.content_hash,
        verifier_ref="independent-verifier",
        verified_at=NOW + timedelta(seconds=20),
        policy_version="governed-memory-fabric:v1",
    )
    return MemoryApprovalVerificationService().verify(
        MemoryPromotionRequest(
            candidate=candidate,
            approval_record=approval,
            verification_record=verification,
            requested_at=NOW + timedelta(seconds=30),
            policy_version="governed-memory-fabric:v1",
        )
    )


def test_backtest_uses_closed_history_and_next_bar_open_fill() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "106", "99", "105"),
        candle(2, "105", "112", "104", "110"),
    )
    observed_lengths: list[int] = []

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        observed_lengths.append(len(history))
        assert history[:] == candles[: len(history)]
        with pytest.raises(IndexError):
            _ = history[len(history)]
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="hotusdt",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert observed_lengths == [1, 2, 3]
    assert result.symbol == "HOTUSDT"
    assert result.trades[0].entry_timestamp == candles[1].timestamp
    assert result.trades[0].entry_price == Decimal("100.0500")
    assert result.trades[0].exit_price == Decimal("109.9450")
    assert result.trades[0].exit_reason is BacktestExitReason.TARGET
    assert result.trades[0].attribution.strategy_id == "UNSPECIFIED_STRATEGY"
    assert result.trades[0].attribution.strategy_config_version == "1"
    assert result.trades[0].attribution.strategy_config_hash == "default"
    assert result.trades[0].attribution.symbol == "HOTUSDT"
    assert result.trades[0].attribution.timeframe == "1h"
    assert result.trades[0].attribution.decision_id == "decision:signal-1"
    assert result.trades[0].entry_reason == ("BACKTEST_SIGNAL",)
    assert result.trades[0].gross_pnl_usdt == Decimal("10.0000000")
    assert result.trades[0].fee_cost_usdt == Decimal("0.2099950")
    assert result.trades[0].slippage_cost_usdt == Decimal("0.1050000")
    assert result.trades[0].funding_cost_usdt == Decimal("0")
    assert result.trades[0].realized_r_multiple == (
        result.trades[0].net_pnl_usdt / Decimal("5.0500")
    )
    assert result.trades[0].maximum_favorable_excursion == Decimal("11.9500")
    assert result.trades[0].maximum_adverse_excursion == Decimal("1.0500")
    assert result.trades[0].holding_period == 3600
    assert result.trades[0].MFE == Decimal("11.9500")
    assert result.trades[0].MAE == Decimal("1.0500")
    assert result.trades[0].holding_time == 3600
    assert result.trades[0].gross_pnl == Decimal("10.0000000")
    assert result.trades[0].fees == Decimal("0.2099950")
    assert result.trades[0].slippage == Decimal("0.1050000")
    assert result.trades[0].net_pnl == result.trades[0].net_pnl_usdt
    assert result.trades[0].risk_at_entry == Decimal("5.0500")
    assert result.trades[0].planned_rr == Decimal("1.970297029702970297029702970")
    assert result.trades[0].entry_score == Decimal("82")
    assert result.trades[0].evidence_score == Decimal("71")
    assert result.trades[0].dge_status == "DGE_PASS"
    assert result.trades[0].blocker_history == ()
    assert result.trades[0].direction.value == "LONG"
    assert result.trade_outcomes[0].trade_id == "trade:signal-1"
    assert result.trade_outcomes[0].strategy_id == "UNSPECIFIED_STRATEGY"
    assert result.trade_outcomes[0].entry_score == Decimal("82")
    assert result.trade_outcomes[0].evidence_score == Decimal("71")
    assert result.trade_outcomes[0].dge_status == "DGE_PASS"
    assert result.trade_outcomes[0].blocker_history == ()
    assert result.metrics.market == "SPOT"
    assert result.metrics.sortino is None
    assert result.metrics.expectancy_r == pytest.approx(1.9178227722772278)
    assert result.metrics.average_win_usdt == pytest.approx(9.685005)
    assert result.metrics.average_loss_usdt is None
    assert result.metrics.exposure_ratio == pytest.approx(0.5)
    assert result.metrics.turnover_ratio == pytest.approx(0.209995)
    assert result.metrics.fee_drag_ratio == pytest.approx(0.000209995)
    assert result.metrics.slippage_drag_ratio == pytest.approx(0.000105)
    assert result.metrics.average_mae_r == pytest.approx(0.2079207920792079)
    assert result.metrics.average_mfe_capture == pytest.approx(0.810460669456067)
    assert result.metrics.max_consecutive_losses == 0
    assert result.metrics.time_under_water_seconds == 0
    assert result.metrics.dge_saved_loss_usdt == 0.0
    assert result.metrics.dge_missed_profit_usdt == 0.0
    assert result.performance_engine_report.spot_metrics == result.metrics
    assert result.performance_engine_report.futures_metrics is None
    assert result.performance_engine_report.combined_masking_allowed is False
    assert result.metrics.trade_count == 1
    assert result.metrics.buy_and_hold_return > 0.0
    assert result.trade_edge_ledger.by_strategy[0].strategy_id == "UNSPECIFIED_STRATEGY"
    assert result.trade_edge_ledger.by_strategy[0].trade_count == 1
    assert result.trade_edge_ledger.by_strategy[0].gross_pnl_usdt == Decimal(
        "10.0000000"
    )
    assert result.trade_edge_ledger.by_regime[0].regime == "UNKNOWN"
    assert result.trade_edge_ledger.by_symbol[0].symbol == "HOTUSDT"
    assert result.trade_edge_ledger.by_timeframe[0].timeframe == "1h"
    assert result.funnel_telemetry.stage_counts == (
        ("DISCOVERED", 1),
        ("READY_FOR_RISK", 1),
        ("RISK_PASS", 0),
        ("VALIDATION_PASS", 0),
        ("DGE_PASS", 0),
        ("VIRTUAL_ORDER", 1),
        ("FILLED", 1),
        ("CLOSED", 1),
    )
    assert result.funnel_telemetry.reason_code_counts == ()


def test_backtest_path_proves_memory_aware_replay_equivalence() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "106", "99", "105"),
        candle(2, "105", "112", "104", "110"),
    )
    fabric = GovernedMemoryFabric()
    past_candidate = fabric.compile_candidate(memory_intent("backtest-past", NOW))
    past = fabric.validate_candidate(
        past_candidate,
        promotion_verification=memory_promotion_verification(
            past_candidate,
            "approval-1",
            "verification-1",
        ),
    )
    future_candidate = fabric.compile_candidate(
        memory_intent("backtest-future", NOW + timedelta(hours=2))
    )
    future = replace(
        fabric.validate_candidate(
            future_candidate,
            promotion_verification=memory_promotion_verification(
                future_candidate,
                "approval-2",
                "verification-2",
            ),
        ),
        valid_from=NOW,
    )
    records = (past, future)

    def baseline_provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    observed_memory_ids: list[tuple[str, ...]] = []
    observed_blockers: list[tuple[str, ...]] = []

    def memory_aware_provider(
        history: tuple[OHLCVCandle, ...],
    ) -> BacktestIntent | None:
        retrieval = fabric.retrieve(
            records,
            MemoryRetrievalRequest(
                subject_keys=("strategy:backtest_replay",),
                as_of=history[-1].timestamp,
                as_of_system_time=history[-1].timestamp + timedelta(seconds=30),
                cycle_id=f"backtest:{len(history)}",
            ),
        )
        observed_memory_ids.append(
            tuple(record.memory_id for record in retrieval.records)
        )
        observed_blockers.append(retrieval.blockers)
        return baseline_provider(history)

    baseline = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=baseline_provider,
    )
    memory_aware = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=memory_aware_provider,
    )

    assert memory_aware == baseline
    assert observed_memory_ids[0] == ("mem:backtest-past",)
    assert observed_memory_ids[1] == ("mem:backtest-past",)
    assert observed_memory_ids[2] == ("mem:backtest-future", "mem:backtest-past")
    assert observed_blockers[0] == ("MEMORY_FUTURE_LEAKAGE",)
    assert observed_blockers[1] == ("MEMORY_FUTURE_LEAKAGE",)
    assert observed_blockers[2] == ()


def test_trailing_stop_cannot_ratchet_and_trigger_on_same_bar() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "109", "98", "105"),
        candle(2, "105", "106", "101", "103"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        proposed = intent(history[-1].timestamp)
        return (
            replace(proposed, take_profit=Decimal("120")) if len(history) == 1 else None
        )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    trade = result.trades[0]
    assert trade.exit_timestamp == candles[2].timestamp
    assert trade.exit_reason is BacktestExitReason.TRAILING_STOP
    assert trade.exit_price == Decimal("101.9490")
    assert trade.closure_review.trailing_quality == "TRIGGERED"


def test_stop_first_ordering_and_fee_accounting_are_conservative() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "111", "94", "105"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    trade = result.trades[0]
    assert trade.exit_reason is BacktestExitReason.HARD_STOP
    assert trade.entry_fee_usdt == Decimal("0.1000500")
    assert trade.exit_fee_usdt == Decimal("0.0949525")
    assert trade.net_pnl_usdt < Decimal("-5")
    assert result.metrics.max_drawdown > 0.0
    assert result.metrics.win_rate == 0.0


def test_pending_open_position_and_end_of_data_are_audited() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "102", "99", "101"),
        candle(2, "101", "103", "100", "102"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp, f"signal-{len(history)}")

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert result.trades[0].exit_reason is BacktestExitReason.END_OF_DATA
    assert result.trades[0].closure_review.ignored_signals == 2
    assert result.trades[0].blocker_history == ("POSITION_ALREADY_OPEN",)
    assert result.trade_outcomes[0].blocker_history == ("POSITION_ALREADY_OPEN",)
    assert result.rejected_signals[0].blockers == ("POSITION_ALREADY_OPEN",)
    assert result.rejected_signals[-1].blockers == ("POSITION_ALREADY_OPEN",)
    assert result.audit_events[-1]["event_type"] == "END_OF_DATA"


def test_missed_opportunity_ledger_marks_bad_block_when_rejected_trade_would_win() -> (
    None
):
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "111", "99", "110"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return replace(
            intent(history[-1].timestamp),
            signal_id="bad-block",
            timestamp=history[-1].timestamp + timedelta(days=1),
        )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    record = result.missed_opportunity_ledger.records[0]
    assert record.counterfactual_result is MissedOpportunityCategory.BAD_BLOCK
    assert record.forward_realized_r is not None
    assert record.forward_realized_r > 0
    assert record.forward_trade_outcome is not None
    assert record.improvement_candidate_id is not None


def test_missed_opportunity_ledger_marks_good_block_for_losing_rejected_trade() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "94", "95"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return replace(
            intent(history[-1].timestamp),
            signal_id="good-block",
            timestamp=history[-1].timestamp + timedelta(days=1),
        )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    record = result.missed_opportunity_ledger.records[0]
    assert record.counterfactual_result is MissedOpportunityCategory.GOOD_BLOCK
    assert record.forward_realized_r is not None
    assert record.forward_realized_r < 0
    assert record.improvement_candidate_id is None


def test_virtual_exit_engine_emits_time_exit_when_holding_limit_is_reached() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "104", "99", "103"),
        candle(2, "103", "104", "102", "103"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return replace(
            intent(history[-1].timestamp),
            signal_id="time-exit",
            take_profit=Decimal("130"),
            maximum_holding_bars=1,
        )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    trade = result.trades[0]
    assert trade.exit_reason is BacktestExitReason.TIME_EXIT
    assert trade.exit_timestamp == candles[2].timestamp
    assert trade.holding_time == 3600


def test_mismatched_and_last_bar_signals_are_rejected() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
    )

    def mismatched(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) == 1:
            return intent(NOW + timedelta(days=1))
        return intent(history[-1].timestamp, "last-bar")

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=mismatched,
    )

    assert result.rejected_signals[0].blockers == ("SIGNAL_TIMESTAMP_MISMATCH",)
    assert result.rejected_signals[1].blockers == ("NO_NEXT_BAR",)
    assert (
        result.missed_opportunity_ledger.records[1].counterfactual_result
        is MissedOpportunityCategory.INSUFFICIENT_EVIDENCE
    )
    assert result.metrics.trade_count == 0
    assert result.metrics.profit_factor is None
    assert result.metrics.sharpe is None


@pytest.mark.parametrize(
    ("config", "next_open", "blocker"),
    [
        (
            BacktestConfig(),
            "90",
            "INVALID_NEXT_BAR_GEOMETRY",
        ),
        (
            BacktestConfig(initial_cash_usdt=Decimal("50")),
            "100",
            "INSUFFICIENT_BACKTEST_CASH",
        ),
    ],
)
def test_next_bar_fill_is_rejected_when_geometry_or_cash_changed(
    config: BacktestConfig,
    next_open: str,
    blocker: str,
) -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, next_open, "101", "89", "100"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine(config).run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert blocker in result.rejected_signals[0].blockers
    assert [event["event_type"] for event in result.audit_events[:2]] == [
        "OPPORTUNITY_OBSERVED_PRE_VETO",
        "ENTRY_REJECTED",
    ]
    observation = result.pre_veto_opportunity_ledger.records[0]
    review = result.missed_opportunity_ledger.records[0]
    assert observation.blockers == ()
    assert observation.assessment_status == "PENDING_FORWARD_REVIEW"
    assert review.pre_veto_observation_id == observation.observation_id
    assert result.metrics.trade_count == 0


def test_backtest_rejects_futures_replay_without_realism_evidence() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return replace(intent(history[-1].timestamp), market="USD_M_FUTURES")

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert result.rejected_signals[0].blockers == ("DATA_UNAVAILABLE",)
    assert result.metrics.trade_count == 0
    assert result.metrics.market == "USD_M_FUTURES"
    assert result.performance_engine_report.spot_metrics is None
    assert result.performance_engine_report.futures_metrics == result.metrics


def test_backtest_rejects_below_minimum_notional_and_step_size_zero_fill() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    minimum_notional = BacktestEngine(
        BacktestConfig(quantity=Decimal("0.01"), minimum_notional=Decimal("5"))
    ).run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )
    rounded_zero = BacktestEngine(
        BacktestConfig(quantity=Decimal("0.5"), step_size=Decimal("1"))
    ).run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert minimum_notional.rejected_signals[0].blockers == (
        "MIN_NOTIONAL_NOT_REACHED",
    )
    assert rounded_zero.rejected_signals[0].blockers == (
        "STEP_SIZE_ROUNDED_QUANTITY_IS_ZERO",
        "MIN_NOTIONAL_NOT_REACHED",
    )


def test_backtest_result_persists_as_redacted_jsonl(tmp_path: Path) -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "111", "99", "110"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )
    output = tmp_path / "backtests.jsonl"
    BacktestAuditWriter(JsonlAuditStore(output)).append(result)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_type"] == "BACKTEST_RESULT"
    assert payload["payload"]["result"]["metrics"]["trade_count"] == 1
    assert payload["payload"]["result"]["metrics"]["market"] == "SPOT"
    assert payload["payload"]["result"]["metrics"]["expectancy_r"] == pytest.approx(
        1.9178227722772276
    )
    assert payload["payload"]["result"]["metrics"]["average_win_usdt"] == pytest.approx(
        9.685005
    )
    assert payload["payload"]["result"]["metrics"]["average_loss_usdt"] is None
    assert payload["payload"]["result"]["metrics"]["exposure_ratio"] == 0.0
    assert payload["payload"]["result"]["metrics"]["turnover_ratio"] == pytest.approx(
        0.209995
    )
    assert payload["payload"]["result"]["metrics"]["fee_drag_ratio"] == pytest.approx(
        0.000209995
    )
    assert payload["payload"]["result"]["metrics"][
        "slippage_drag_ratio"
    ] == pytest.approx(0.000105)
    assert payload["payload"]["result"]["metrics"]["max_consecutive_losses"] == 0
    assert payload["payload"]["result"]["metrics"]["time_under_water_seconds"] == 0
    assert payload["payload"]["result"]["metrics"]["dge_saved_loss_usdt"] == 0.0
    persisted_observation = payload["payload"]["result"]["pre_veto_opportunity_ledger"][
        "records"
    ][0]
    assert persisted_observation["blockers"] == []
    assert persisted_observation["assessment_status"] == "PENDING_FORWARD_REVIEW"
    assert persisted_observation["execution_allowed"] is False
    assert payload["payload"]["result"]["metrics"]["dge_missed_profit_usdt"] == 0.0
    assert (
        payload["payload"]["result"]["performance_engine_report"]["spot_metrics"][
            "market"
        ]
        == "SPOT"
    )
    assert (
        payload["payload"]["result"]["performance_engine_report"]["futures_metrics"]
        is None
    )
    assert (
        payload["payload"]["result"]["performance_engine_report"][
            "combined_masking_allowed"
        ]
        is False
    )
    assert payload["payload"]["result"]["trades"][0]["signal_id"] == "signal-1"
    assert payload["payload"]["result"]["missed_opportunity_ledger"] == {"records": []}
    assert payload["payload"]["result"]["trades"][0]["attribution"] == {
        "decision_id": "decision:signal-1",
        "market": "SPOT",
        "opportunity_id": "opportunity:signal-1",
        "regime": "UNKNOWN",
        "snapshot_id": "snapshot:HOTUSDT:1h:signal-1",
        "strategy_config_hash": "default",
        "strategy_config_version": "1",
        "strategy_id": "UNSPECIFIED_STRATEGY",
        "strategy_version": "1",
        "symbol": "HOTUSDT",
        "timeframe": "1h",
    }
    assert payload["payload"]["result"]["trades"][0]["entry_reason"] == [
        "BACKTEST_SIGNAL"
    ]
    assert payload["payload"]["result"]["trades"][0]["exit_reason"] == "TARGET"
    assert payload["payload"]["result"]["trades"][0]["MAE"] == "1.0500000000000000"
    assert payload["payload"]["result"]["trades"][0]["MFE"] == "10.9500000000000000"
    assert payload["payload"]["result"]["trades"][0]["holding_time"] == 0
    assert (
        payload["payload"]["result"]["trades"][0]["gross_pnl"]
        == "10.0000000000000000000"
    )
    assert payload["payload"]["result"]["trades"][0]["fees"] == "0.2099950000000000000"
    assert payload["payload"]["result"]["trades"][0]["slippage"] == "0.1050000000000000"
    assert (
        payload["payload"]["result"]["trades"][0]["net_pnl"] == "9.6850050000000000000"
    )
    assert (
        payload["payload"]["result"]["trades"][0]["risk_at_entry"]
        == "5.0500000000000000"
    )
    assert (
        payload["payload"]["result"]["trades"][0]["planned_rr"]
        == "1.970297029702970297029702970"
    )
    assert payload["payload"]["result"]["trades"][0]["entry_score"] == "82"
    assert payload["payload"]["result"]["trades"][0]["evidence_score"] == "71"
    assert payload["payload"]["result"]["trades"][0]["dge_status"] == "DGE_PASS"
    assert payload["payload"]["result"]["trades"][0]["blocker_history"] == []
    assert payload["payload"]["result"]["trade_outcomes"][0] == {
        "blocker_history": [],
        "dge_status": "DGE_PASS",
        "direction": "LONG",
        "entry_price": "100.05000000",
        "entry_reason": ["BACKTEST_SIGNAL"],
        "entry_score": "82",
        "entry_time": "2026-01-01T01:00:00+00:00",
        "evidence_score": "71",
        "exit_price": "109.94500000",
        "exit_reason": "TARGET",
        "exit_time": "2026-01-01T01:00:00+00:00",
        "fee_cost": "0.2099950000000000000",
        "funding_cost": "0",
        "gross_pnl": "10.0000000000000000000",
        "mae": "1.0500000000000000",
        "market": "SPOT",
        "mfe": "10.9500000000000000",
        "net_pnl": "9.6850050000000000000",
        "planned_rr": "1.970297029702970297029702970",
        "realized_rr": "1.917822772277227722772277228",
        "regime": "UNKNOWN",
        "risk_at_entry": "5.0500000000000000",
        "slippage_cost": "0.1050000000000000",
        "strategy_id": "UNSPECIFIED_STRATEGY",
        "strategy_version": "1",
        "symbol": "HOTUSDT",
        "trade_id": "trade:signal-1",
    }
    assert (
        payload["payload"]["result"]["trades"][0]["gross_pnl_usdt"]
        == "10.0000000000000000000"
    )
    assert (
        payload["payload"]["result"]["trades"][0]["slippage_cost_usdt"]
        == "0.1050000000000000"
    )
    assert payload["payload"]["result"]["trade_edge_ledger"]["by_strategy"] == [
        {
            "average_holding_period": "0",
            "average_maximum_adverse_excursion": "1.0500000000000000",
            "average_maximum_favorable_excursion": "10.9500000000000000",
            "average_realized_r_multiple": "1.917822772277227722772277228",
            "fee_cost_usdt": "0.2099950000000000000",
            "funding_cost_usdt": "0",
            "gross_pnl_usdt": "10.0000000000000000000",
            "net_pnl_usdt": "9.6850050000000000000",
            "regime": None,
            "slippage_cost_usdt": "0.1050000000000000",
            "strategy_id": "UNSPECIFIED_STRATEGY",
            "symbol": None,
            "timeframe": None,
            "trade_count": 1,
        }
    ]
    assert payload["payload"]["result"]["funnel_telemetry"]["stage_counts"] == [
        ["DISCOVERED", 1],
        ["READY_FOR_RISK", 1],
        ["RISK_PASS", 0],
        ["VALIDATION_PASS", 0],
        ["DGE_PASS", 0],
        ["VIRTUAL_ORDER", 1],
        ["FILLED", 1],
        ["CLOSED", 1],
    ]

    bounded_output = tmp_path / "bounded-backtests.jsonl"
    bounded_result = replace(
        result,
        audit_events=({"large_evidence": "x" * 1_000_000},),
    )
    bounded_store = JsonlAuditStore(bounded_output, max_event_bytes=100_000)
    BacktestAuditWriter(bounded_store).append(bounded_result)
    bounded_line = bounded_output.read_bytes()
    bounded = json.loads(bounded_line)["payload"]["result"]
    assert len(bounded_line) <= bounded_store.max_event_bytes
    assert bounded["detail_level"] == "BOUNDED_SUMMARY"
    assert bounded["collection_counts"]["audit_events"] == 1
    assert bounded["collection_counts"]["pre_veto_opportunity_records"] == 1
    assert len(bounded["collection_sha256"]["audit_events"]) == 64
    assert len(bounded["full_result_sha256"]) == 64
    assert "audit_events" not in bounded


@pytest.mark.parametrize(
    "candles",
    [
        (candle(0, "100", "101", "99", "100"),),
        (
            candle(1, "100", "101", "99", "100"),
            candle(0, "100", "101", "99", "100"),
        ),
    ],
)
def test_backtest_rejects_insufficient_or_unsorted_data(
    candles: tuple[OHLCVCandle, ...],
) -> None:
    with pytest.raises(ValueError, match=r"at least two|strictly chronological"):
        BacktestEngine().run(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=candles,
            signal_provider=lambda _history: None,
        )


def test_backtest_contracts_reject_unsafe_assumptions() -> None:
    with pytest.raises(ValueError, match="initial cash"):
        BacktestConfig(initial_cash_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="fee_ratio"):
        BacktestConfig(fee_ratio=Decimal("0"))
    with pytest.raises(ValueError, match="fee_ratio"):
        BacktestConfig(fee_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="slippage_ratio"):
        BacktestConfig(slippage_ratio=Decimal("0"))
    with pytest.raises(ValueError, match="slippage_ratio"):
        BacktestConfig(slippage_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="trailing_multiplier"):
        BacktestConfig(trailing_multiplier=Decimal("0"))
    with pytest.raises(ValueError, match="tick_size"):
        BacktestConfig(tick_size=Decimal("0"))
    with pytest.raises(ValueError, match="step_size"):
        BacktestConfig(step_size=Decimal("0"))
    with pytest.raises(ValueError, match="minimum_notional"):
        BacktestConfig(minimum_notional=Decimal("0"))
    with pytest.raises(ValueError, match="signal identity"):
        replace(intent(NOW), signal_id="")
    with pytest.raises(ValueError, match="unsupported virtual-market stages"):
        replace(intent(NOW), funnel_stages=("DISCOVERED", "FILLED"))
    with pytest.raises(ValueError, match="strategy_config_hash"):
        replace(intent(NOW), strategy_config_hash="")
    with pytest.raises(ValueError, match="entry_score"):
        replace(intent(NOW), entry_score=Decimal("-1"))
    with pytest.raises(ValueError, match="evidence_score"):
        replace(intent(NOW), evidence_score=Decimal("-1"))
    with pytest.raises(ValueError, match="dge_status"):
        replace(intent(NOW), dge_status="")
    with pytest.raises(ValueError, match="blocker_history"):
        replace(intent(NOW), blocker_history=("A", "A"))
    with pytest.raises(ValueError, match="timeframe"):
        BacktestEngine().run(
            symbol="HOTUSDT",
            timeframe="",
            candles=(
                candle(0, "100", "101", "99", "100"),
                candle(1, "100", "101", "99", "100"),
            ),
            signal_provider=lambda _history: None,
        )


def test_backtest_honors_profile_exit_overrides_deterministically() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "103", "99", "102"),
        candle(2, "102", "103", "100", "101"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return replace(
            intent(history[-1].timestamp),
            signal_id="profile-exit",
            strategy_id="trend_continuation",
            strategy_config_version="2",
            strategy_config_hash="abc123",
            breakeven_trigger_r=Decimal("0.4"),
            trailing_atr_multiple=Decimal("0.5"),
            maximum_holding_bars=2,
        )

    first = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )
    second = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert first == second
    trade = first.trades[0]
    assert trade.exit_reason is BacktestExitReason.TRAILING_STOP
    assert trade.attribution.strategy_config_version == "2"
    assert trade.attribution.strategy_config_hash == "abc123"

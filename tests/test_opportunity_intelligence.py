"""Deterministic opportunity-intelligence and post-hoc outcome proofs."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import ai4binance.opportunity_intelligence as opportunity_intelligence
from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.opportunity_intelligence import (
    CandleDirection,
    CandlestickPattern,
    ChartPatternLifecycleState,
    MultiTimeframeAlignmentState,
    OpportunityEventType,
    OpportunityLifecycleEvent,
    OpportunityLifecycleLedger,
    analyze_candlestick,
    build_multi_timeframe_diagnostic,
    candle_geometry,
    detect_chart_pattern,
    opportunity_event_id,
)
from ai4binance.opportunity_ledger import OpportunityLedgerWriter
from ai4binance.opportunity_outcomes import (
    MissedOpportunityAssessment,
    MissedOpportunityCause,
    OpportunityOutcomeClass,
    OpportunityOutcomeStatus,
    classify_missed_opportunity,
    evaluate_opportunity_outcome,
)
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle

DECISION_TIME = datetime(2026, 9, 11, 9, 45, tzinfo=UTC)


def test_opportunity_intelligence_contracts_are_public_module_exports() -> None:
    assert "build_multi_timeframe_diagnostic" in opportunity_intelligence.__all__
    assert "OpportunityLifecycleLedger" in opportunity_intelligence.__all__


def candle(
    timestamp: datetime,
    *,
    open_: str = "100",
    high: str = "102",
    low: str = "98",
    close: str = "101",
    volume: str = "100",
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=timestamp,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def multi_timeframe_snapshot(
    *,
    missing: str | None = None,
    stale: str | None = None,
) -> MarketSnapshot:
    rows = {
        "15m": (
            candle(datetime(2026, 9, 11, 9, 15, tzinfo=UTC), close="100"),
            candle(datetime(2026, 9, 11, 9, 30, tzinfo=UTC), close="101"),
        ),
        "1h": (
            candle(datetime(2026, 9, 11, 7, 0, tzinfo=UTC), close="100"),
            candle(datetime(2026, 9, 11, 8, 0, tzinfo=UTC), close="101"),
            candle(
                datetime(2026, 9, 11, 9, 0, tzinfo=UTC),
                high="1000",
                close="999",
            ),
        ),
        "4h": (
            candle(datetime(2026, 9, 11, 0, 0, tzinfo=UTC), close="100"),
            candle(datetime(2026, 9, 11, 4, 0, tzinfo=UTC), close="101"),
            candle(
                datetime(2026, 9, 11, 8, 0, tzinfo=UTC),
                high="1000",
                close="999",
            ),
        ),
    }
    if missing is not None:
        rows.pop(missing)
    freshness = {timeframe: {"stale": timeframe == stale} for timeframe in rows}
    return MarketSnapshot(
        snapshot_id="mtf-boundary",
        created_at=DECISION_TIME,
        exchange="Binance",
        market_type="SPOT",
        symbol="BTCUSDT",
        timeframes=tuple(rows),
        ohlcv_by_timeframe=rows,
        latest_price=Decimal("101"),
        bid=Decimal("100.9"),
        ask=Decimal("101.1"),
        spread=Decimal("0.2"),
        data_freshness=freshness,
        data_quality=DataQuality.DATA_VALID,
    )


def test_multi_timeframe_alignment_cannot_see_future_closes() -> None:
    diagnostic = build_multi_timeframe_diagnostic(multi_timeframe_snapshot())

    references = {item.timeframe: item for item in diagnostic.candle_references}
    assert references["15m"].open_time.hour == 9
    assert references["15m"].open_time.minute == 30
    assert references["1h"].open_time.hour == 8
    assert references["4h"].open_time.hour == 4
    assert all(item.close_time <= DECISION_TIME for item in references.values())
    assert diagnostic.alignment_status is MultiTimeframeAlignmentState.ALIGNED
    assert diagnostic.complete is True
    assert diagnostic.execution_allowed is False
    assert diagnostic.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_multi_timeframe_exact_close_missing_stale_and_determinism() -> None:
    snapshot = multi_timeframe_snapshot()
    at_boundary = build_multi_timeframe_diagnostic(
        snapshot,
        decision_time=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
    )
    one_hour = next(
        item for item in at_boundary.candle_references if item.timeframe == "1h"
    )
    assert one_hour.open_time.hour == 9
    assert at_boundary == build_multi_timeframe_diagnostic(
        snapshot,
        decision_time=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
    )

    missing = build_multi_timeframe_diagnostic(multi_timeframe_snapshot(missing="4h"))
    assert missing.alignment_status is MultiTimeframeAlignmentState.INSUFFICIENT_DATA
    assert "MISSING_CLOSED_TIMEFRAME:4h" in missing.blockers

    stale = build_multi_timeframe_diagnostic(multi_timeframe_snapshot(stale="1h"))
    assert "STALE_TIMEFRAME:1h" in stale.blockers


def test_multi_timeframe_relationships_are_not_naive_voting() -> None:
    snapshot = multi_timeframe_snapshot()
    conflicting = build_multi_timeframe_diagnostic(
        snapshot,
        timeframe_votes={"4h": 0.8, "1h": 0.4, "15m": -0.9},
    )
    transitional = build_multi_timeframe_diagnostic(
        snapshot,
        timeframe_votes={"4h": -0.8, "1h": 0.4, "15m": 0.9},
    )
    assert conflicting.alignment_status is MultiTimeframeAlignmentState.CONFLICTING
    assert transitional.alignment_status is MultiTimeframeAlignmentState.TRANSITIONAL


def test_candle_geometry_handles_zero_range_and_contextual_patterns() -> None:
    flat = candle(DECISION_TIME, high="100", low="100", close="100")
    geometry = candle_geometry(flat)
    assert geometry.candle_range == 0
    assert geometry.body_to_range_ratio == 0
    assert geometry.close_location == 0

    previous = candle(
        DECISION_TIME - timedelta(minutes=15),
        open_="105",
        high="106",
        low="99",
        close="100",
    )
    current = candle(
        DECISION_TIME,
        open_="99",
        high="108",
        low="98",
        close="107",
        volume="300",
    )
    evidence = analyze_candlestick((previous, current))
    assert CandlestickPattern.BULLISH_ENGULFING in evidence.patterns
    assert CandlestickPattern.OUTSIDE_BAR in evidence.patterns
    assert evidence.geometry.direction is CandleDirection.BULLISH


def pattern_rows(count: int) -> tuple[OHLCVCandle, ...]:
    rows: list[OHLCVCandle] = []
    start = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)
    for index in range(count):
        high = Decimal("106") if index in {2, 10} else Decimal("103")
        low = Decimal("96") if index == 6 else Decimal("99")
        close = Decimal("95") if index >= 11 else Decimal("101")
        rows.append(
            OHLCVCandle(
                timestamp=start + timedelta(minutes=15 * index),
                open=Decimal("101"),
                high=max(high, close),
                low=min(low, close),
                close=close,
                volume=Decimal("100"),
            )
        )
    return tuple(rows)


def test_chart_pattern_waits_for_pivot_confirmation_without_repainting() -> None:
    forming_rows = pattern_rows(12)
    forming = detect_chart_pattern(
        forming_rows,
        timeframe="15m",
        snapshot_id="pattern-snapshot",
        decision_time=forming_rows[-1].timestamp + timedelta(minutes=15),
    )
    assert forming is not None
    assert forming.pattern_type == "DOUBLE_TOP"
    assert forming.state is ChartPatternLifecycleState.FORMING
    assert forming.pivot_available_time > forming_rows[10].timestamp

    complete_rows = pattern_rows(15)
    confirmed = detect_chart_pattern(
        complete_rows,
        timeframe="15m",
        snapshot_id="pattern-snapshot",
        decision_time=complete_rows[-1].timestamp + timedelta(minutes=15),
    )
    assert confirmed is not None
    assert confirmed.state is ChartPatternLifecycleState.CONFIRMED
    assert confirmed.pivot_available_time <= confirmed.last_observation_time


def lifecycle_event(
    *,
    state: OpportunityLifecycleState,
    event_type: OpportunityEventType,
    minute: int,
) -> OpportunityLifecycleEvent:
    event_time = DECISION_TIME + timedelta(minutes=minute)
    return OpportunityLifecycleEvent(
        event_id=opportunity_event_id(
            "opportunity:1", event_type, event_time, "snapshot:1"
        ),
        event_type=event_type,
        opportunity_id="opportunity:1",
        lifecycle_state=state,
        event_time=event_time,
        cycle_id="cycle:1",
        snapshot_id="snapshot:1",
        reason_codes=("DETERMINISTIC_TEST",),
        evidence_refs=("snapshot:snapshot:1",),
    )


def test_opportunity_lifecycle_is_append_only_idempotent_and_ordered() -> None:
    observed = lifecycle_event(
        state=OpportunityLifecycleState.DISCOVERED,
        event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
        minute=0,
    )
    forming = lifecycle_event(
        state=OpportunityLifecycleState.SETUP_FORMING,
        event_type=OpportunityEventType.OPPORTUNITY_FORMING,
        minute=15,
    )
    ledger = OpportunityLifecycleLedger().append(observed).append(forming)
    assert ledger.first_seen_at("opportunity:1") == DECISION_TIME
    assert ledger.append(forming) is ledger
    with pytest.raises(ValueError, match="transition"):
        ledger.append(
            lifecycle_event(
                state=OpportunityLifecycleState.DISCOVERED,
                event_type=OpportunityEventType.OPPORTUNITY_UPDATED,
                minute=30,
            )
        )
    with pytest.raises(ValueError, match="cannot change content"):
        ledger.append(replace(forming, reason_codes=("CHANGED",)))


def test_opportunity_ledger_writer_persists_exact_event_once(tmp_path: Path) -> None:
    event = lifecycle_event(
        state=OpportunityLifecycleState.DISCOVERED,
        event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
        minute=0,
    )
    path = tmp_path / "opportunity" / "lifecycle.jsonl"
    writer = OpportunityLedgerWriter(path, durable=False)

    assert writer.append(event) is not None
    assert writer.append(event) is None
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def future_rows(count: int) -> tuple[OHLCVCandle, ...]:
    start = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
    highs = ("101", "103", "102", "104")
    lows = ("99", "98", "99", "100")
    return tuple(
        candle(
            start + timedelta(minutes=15 * index),
            high=highs[index],
            low=lows[index],
            close="101",
        )
        for index in range(count)
    )


def test_outcomes_remain_post_hoc_until_horizon_is_complete() -> None:
    pending = evaluate_opportunity_outcome(
        opportunity_id="opportunity:1",
        direction="BULLISH",
        reference_price=Decimal("100"),
        observed_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        future_candles=future_rows(2),
        evaluation_horizon=3,
        dataset_id="dataset:1",
        timeframe="15m",
        invalidation_price=Decimal("97"),
        target_price=Decimal("102.5"),
    )
    assert pending.status is OpportunityOutcomeStatus.PENDING_HORIZON
    assert pending.maximum_favorable_excursion is None

    evaluated = evaluate_opportunity_outcome(
        opportunity_id="opportunity:1",
        direction="BULLISH",
        reference_price=Decimal("100"),
        observed_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        future_candles=future_rows(4),
        evaluation_horizon=3,
        dataset_id="dataset:1",
        timeframe="15m",
        invalidation_price=Decimal("97"),
        target_price=Decimal("102.5"),
    )
    assert evaluated.status is OpportunityOutcomeStatus.EVALUATED
    assert evaluated.maximum_favorable_excursion == Decimal("3")
    assert evaluated.maximum_adverse_excursion == Decimal("2")
    assert evaluated.final_outcome_class is OpportunityOutcomeClass.TARGET_FIRST
    assert evaluated.target_before_invalidation is True
    assert evaluated.evaluation_completed_at is not None

    risk_review = classify_missed_opportunity(
        opportunity_id="opportunity:1",
        symbol="BTCUSDT",
        market="SPOT",
        timeframe="15m",
        window_start=evaluated.evaluation_started_at,
        window_end=evaluated.evaluation_completed_at,
        counterfactual_detection_time=evaluated.evaluation_started_at,
        actual_detection_time=None,
        cause=MissedOpportunityCause.RISK_BLOCKED,
        outcome=evaluated,
        blocking_reason_codes=("RISK_VETO",),
    )
    assert risk_review.assessment is MissedOpportunityAssessment.UNRESOLVED

    detector_review = classify_missed_opportunity(
        opportunity_id="opportunity:1",
        symbol="BTCUSDT",
        market="SPOT",
        timeframe="15m",
        window_start=evaluated.evaluation_started_at,
        window_end=evaluated.evaluation_completed_at,
        counterfactual_detection_time=evaluated.evaluation_started_at,
        actual_detection_time=None,
        cause=MissedOpportunityCause.PATTERN_NOT_DETECTED,
        outcome=evaluated,
    )
    assert (
        detector_review.assessment
        is MissedOpportunityAssessment.POSSIBLE_FALSE_NEGATIVE
    )


def test_hot_path_does_not_import_post_outcome_contracts() -> None:
    source = Path("src/ai4binance/opportunity_radar.py").read_text(encoding="utf-8")
    assert "opportunity_outcomes" not in source

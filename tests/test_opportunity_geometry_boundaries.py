"""Opportunity evidence rejects inconsistent geometry and premature confirmation."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.opportunity_intelligence import (
    CandleDirection,
    CandlestickPattern,
    ChartPatternLifecycleState,
    OpportunityEventType,
    OpportunityLifecycleLedger,
    analyze_candlestick,
    build_multi_timeframe_diagnostic,
    candle_geometry,
    detect_chart_pattern,
)
from tests.test_opportunity_intelligence import (
    DECISION_TIME,
    candle,
    lifecycle_event,
    multi_timeframe_snapshot,
    pattern_rows,
)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("body_size", Decimal(-1), "negative"),
        ("close_location", Decimal(2), "bounded"),
        ("range_vs_atr", Decimal("NaN"), "finite"),
        ("relative_volume", Decimal(-1), "finite"),
    ],
)
def test_candle_geometry_rejects_invalid_magnitudes_and_ratios(
    field: str, value: object, message: str
) -> None:
    geometry = candle_geometry(candle(DECISION_TIME))
    with pytest.raises(ValueError, match=message):
        replace(geometry, **{field: cast(Any, value)})


def test_timeframe_diagnostic_requires_unique_aware_closed_candle_identity() -> None:
    diagnostic = build_multi_timeframe_diagnostic(
        multi_timeframe_snapshot(), decision_time=DECISION_TIME
    )
    reference = diagnostic.candle_references[0]
    change: dict[str, Any]
    for change, message in (
        ({"timeframe": ""}, "identity"),
        ({"close_time": reference.open_time}, "follow open"),
        ({"open_time": datetime(2026, 1, 1)}, "timezone-aware"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(reference, **change)
    for change, message in (
        ({"source_snapshot_id": ""}, "identity"),
        ({"candle_references": (reference, reference)}, "unique"),
        ({"execution_allowed": True}, "execution"),
        ({"live_eligibility_status": "LIVE"}, "execution"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(diagnostic, **change)


def test_candlestick_engulfing_and_duplicate_evidence() -> None:
    previous = candle(
        DECISION_TIME - timedelta(minutes=15),
        open_="99",
        close="102",
        high="103",
        low="98",
    )
    current = candle(DECISION_TIME, open_="102", close="98", high="103", low="97")
    evidence = analyze_candlestick((previous, current))
    assert CandlestickPattern.BEARISH_ENGULFING in evidence.patterns
    assert evidence.geometry.direction is CandleDirection.BEARISH
    with pytest.raises(ValueError, match="unique"):
        replace(evidence, patterns=(CandlestickPattern.BEARISH_ENGULFING,) * 2)
    with pytest.raises(ValueError, match="two closed candles"):
        analyze_candlestick((current,))


def test_chart_pattern_contract_rejects_premature_confirmation() -> None:
    rows = pattern_rows(15)
    pattern = detect_chart_pattern(
        rows,
        timeframe="15m",
        snapshot_id="snapshot",
        decision_time=rows[-1].timestamp + timedelta(minutes=15),
    )
    assert pattern is not None
    for change, message in (
        ({"pattern_id": ""}, "identity"),
        ({"formation_progress": Decimal(2)}, "0..1"),
        ({"anchor_points": ()}, "anchors"),
        (
            {
                "pivot_available_time": pattern.last_observation_time
                + timedelta(minutes=1)
            },
            "before pivot",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            replace(pattern, **change)
    for options, message in (
        ({"timeframe": "invalid"}, "unsupported"),
        ({"pivot_confirmation_bars": 0}, "confirmation"),
        ({"expiry_bars": 1}, "expiry"),
    ):
        with pytest.raises(ValueError, match=message):
            detect_chart_pattern(
                rows,
                **cast(
                    dict[str, Any],
                    (
                        {
                            "timeframe": "15m",
                            "snapshot_id": "snapshot",
                            "decision_time": DECISION_TIME,
                        }
                        | options
                    ),
                ),
            )


def test_lifecycle_contract_rejects_invalid_lineage_and_authority() -> None:
    event = lifecycle_event(
        state=OpportunityLifecycleState.DISCOVERED,
        event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
        minute=0,
    )
    for change, message in (
        ({"event_id": ""}, "identity"),
        ({"reason_codes": (" ",)}, "blank"),
        ({"reason_codes": ("A", "A")}, "unique"),
        ({"decision_id": " "}, "lineage"),
        ({"execution_allowed": True}, "execution"),
        ({"live_eligibility_status": "LIVE"}, "execution"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(event, **change)
    assert OpportunityLifecycleLedger().first_seen_at("missing") is None


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (3, ChartPatternLifecycleState.EXPIRED),
        (4, ChartPatternLifecycleState.FAILED),
        (5, ChartPatternLifecycleState.POTENTIAL),
    ],
)
def test_unconfirmed_chart_patterns_expire_without_becoming_confirmed(
    expiry: int, expected: ChartPatternLifecycleState
) -> None:
    rows = tuple(
        replace(item, close=Decimal(101), low=min(item.low, Decimal(99)))
        for item in pattern_rows(15)
    )
    result = detect_chart_pattern(
        rows,
        timeframe="15m",
        snapshot_id="snapshot",
        decision_time=rows[-1].timestamp + timedelta(minutes=15),
        expiry_bars=expiry,
    )
    assert result is not None
    assert result.state is expected


def test_multi_timeframe_neutral_votes_and_invalid_sequence_remain_visible() -> None:
    snapshot = multi_timeframe_snapshot()
    partial = build_multi_timeframe_diagnostic(
        snapshot, timeframe_votes={"4h": 1, "1h": 1, "15m": 0}
    )
    assert partial.alignment_status.value == "PARTIALLY_ALIGNED"
    assert partial.to_payload()["candle_references"]
    unknown = build_multi_timeframe_diagnostic(
        snapshot, timeframe_votes={"4h": 0, "1h": 0, "15m": 0}
    )
    assert unknown.alignment_status.value == "UNKNOWN"
    with pytest.raises(ValueError, match="cannot be negative"):
        build_multi_timeframe_diagnostic(snapshot, maximum_stale_bars=-1)
    rows = dict(snapshot.ohlcv_by_timeframe)
    rows["15m"] = tuple(reversed(rows["15m"]))
    result = build_multi_timeframe_diagnostic(
        replace(snapshot, ohlcv_by_timeframe=rows)
    )
    assert "TIMEFRAME_SEQUENCE_INVALID:15m" in result.blockers


def test_candlestick_rejection_and_range_contraction_are_explicit() -> None:
    previous = candle(DECISION_TIME - timedelta(minutes=15), high="110", low="90")
    current = candle(DECISION_TIME, high="103", low="99", open_="100", close="100")
    evidence = analyze_candlestick((previous, current))
    assert {
        CandlestickPattern.INDECISION,
        CandlestickPattern.REJECTION,
        CandlestickPattern.INSIDE_BAR,
        CandlestickPattern.RANGE_CONTRACTION,
    }.issubset(evidence.patterns)


def test_chart_pattern_rejects_short_history_and_detects_double_bottom() -> None:
    assert (
        detect_chart_pattern(
            pattern_rows(5),
            timeframe="15m",
            snapshot_id="short",
            decision_time=DECISION_TIME,
        )
        is None
    )
    rows = []
    for index in range(15):
        rows.append(
            candle(
                DECISION_TIME + timedelta(minutes=15 * index),
                high="112" if index == 6 else "104",
                low="95" if index in {2, 10} else "99",
            )
        )
    result = detect_chart_pattern(
        rows,
        timeframe="15m",
        snapshot_id="bottom",
        decision_time=rows[-1].timestamp + timedelta(minutes=15),
    )
    assert result is not None
    assert result.pattern_type == "DOUBLE_BOTTOM"
    assert result.directional_bias is CandleDirection.BULLISH
    assert result.state is ChartPatternLifecycleState.POTENTIAL


def test_lifecycle_rejects_time_regression_and_terminal_reentry() -> None:
    observed = lifecycle_event(
        state=OpportunityLifecycleState.DISCOVERED,
        event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
        minute=0,
    )
    ledger = OpportunityLifecycleLedger().append(observed)
    same_state = replace(
        observed,
        event_id="same-state",
        event_time=observed.event_time + timedelta(minutes=1),
    )
    ledger = ledger.append(same_state)
    with pytest.raises(ValueError, match="time cannot regress"):
        ledger.append(
            replace(
                observed,
                event_id="earlier",
                event_time=observed.event_time - timedelta(minutes=1),
            )
        )
    closed = replace(
        same_state, event_id="closed", lifecycle_state=OpportunityLifecycleState.CLOSED
    )
    terminal = ledger.append(closed)
    with pytest.raises(ValueError, match="transition is invalid"):
        terminal.append(replace(same_state, event_id="reentry"))
    with pytest.raises(ValueError, match="begin with observation"):
        OpportunityLifecycleLedger().append(closed)
    blocked = ledger.append(
        replace(
            same_state,
            event_id="blocked",
            lifecycle_state=OpportunityLifecycleState.BLOCKED,
        )
    )
    restored = blocked.append(
        replace(
            same_state,
            event_id="watch",
            lifecycle_state=OpportunityLifecycleState.WATCH_ONLY,
        )
    )
    assert restored.events[-1].lifecycle_state is OpportunityLifecycleState.WATCH_ONLY

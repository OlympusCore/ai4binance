"""Causal historical regime and playbook-quality decision tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.schemas import OHLCVCandle
from ai4binance.strategies.rules import (
    HistoricalRegime,
    historical_playbook_decision,
    level_reaction_statistics,
)


def candles(
    *,
    trending: bool,
    high_volatility: bool = False,
) -> tuple[OHLCVCandle, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    output: list[OHLCVCandle] = []
    for index in range(50):
        base = Decimal("100") + (Decimal(index) * Decimal("2") if trending else 0)
        width = Decimal("6") if high_volatility else Decimal("0.5")
        output.append(
            OHLCVCandle(
                timestamp=start + timedelta(hours=index),
                open=base - Decimal("0.2"),
                high=base + width,
                low=base - width,
                close=base,
                volume=Decimal("2000") if index == 49 else Decimal("1000"),
            )
        )
    return tuple(output)


def test_historical_decision_blocks_short_history_and_range_trend_setup() -> None:
    short = historical_playbook_decision(
        "trend_continuation",
        candles(trending=False)[:5],
    )
    assert short.blockers == ("INSUFFICIENT_PLAYBOOK_HISTORY",)

    ranged = historical_playbook_decision(
        "trend_continuation",
        candles(trending=False),
    )
    assert ranged.regime is HistoricalRegime.RANGE
    assert ranged.blockers == ("REGIME_BLOCKED:RANGE",)


def test_historical_decision_requires_volume_and_evaluates_all_playbooks() -> None:
    trend = candles(trending=True)
    continuation = historical_playbook_decision("trend_continuation", trend)
    assert continuation.regime is HistoricalRegime.TREND
    assert continuation.triggered is True

    low_volume = (*trend[:-1], replace(trend[-1], volume=Decimal("100")))
    weak = historical_playbook_decision("trend_continuation", low_volume)
    assert weak.blockers == ("RELATIVE_VOLUME_INSUFFICIENT",)

    for playbook in (
        "pullback_continuation",
        "breakout_retest",
        "support_reclaim",
    ):
        decision = historical_playbook_decision(playbook, trend)
        assert decision.regime is HistoricalRegime.TREND

    volatile = candles(trending=False, high_volatility=True)
    reversal = historical_playbook_decision("failed_breakout_reversal", volatile)
    assert reversal.regime is HistoricalRegime.HIGH_VOLATILITY

    unknown = historical_playbook_decision("unknown", trend)
    assert unknown.triggered is False
    assert unknown.blockers == ("REGIME_BLOCKED:TREND",)


def test_level_reaction_statistics_requires_repeated_successful_reactions() -> None:
    history = [
        replace(
            item,
            open=Decimal("105"),
            high=Decimal("105.5"),
            low=Decimal("104.5"),
            close=Decimal("105"),
        )
        for item in candles(trending=False)
    ]
    level = Decimal("100")
    for index in (15, 25, 35):
        history[index] = replace(
            history[index],
            open=level,
            low=Decimal("99.7"),
            high=Decimal("100.1"),
            close=level,
        )
        history[index + 1] = replace(
            history[index + 1],
            open=level,
            high=Decimal("101.2"),
            low=Decimal("99.5"),
            close=Decimal("101"),
        )

    validated = level_reaction_statistics(tuple(history), level, support=True)
    isolated = level_reaction_statistics(tuple(history), Decimal("80"), support=True)

    assert validated.touch_count >= 3
    assert validated.success_rate >= 0.6
    assert validated.validated is True
    assert isolated.validated is False

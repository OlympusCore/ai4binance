"""Causal historical regime and playbook-quality decision tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.schemas import OHLCVCandle
from ai4binance.strategies.registry import build_playbook_registry
from ai4binance.strategies.rules import (
    HistoricalRegime,
    historical_playbook_decision,
    level_reaction_statistics,
    setup_pattern_type,
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
    assert ranged.regime_strategy_reason_code == "REGIME_STRATEGY_INCOMPATIBLE"


def test_historical_decision_requires_volume_and_evaluates_all_playbooks() -> None:
    trend = candles(trending=True)
    continuation = historical_playbook_decision("trend_continuation", trend)
    assert continuation.regime is HistoricalRegime.TREND
    assert continuation.triggered is True
    assert continuation.regime_strategy_reason_code == "REGIME_STRATEGY_ELIGIBLE"

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
    assert unknown.regime_strategy_reason_code == "REGIME_STRATEGY_INCOMPATIBLE"


def test_strategy_registry_declares_canonical_compatible_regimes() -> None:
    registry = build_playbook_registry()

    assert registry.get("trend_continuation").compatible_regimes == ("TREND",)
    assert registry.get("compression_breakout").compatible_regimes == (
        "RANGE",
        "HIGH_VOLATILITY",
    )
    assert setup_pattern_type("breakout_retest") == "REVERSAL_PATTERN"
    assert setup_pattern_type("support_reclaim") == "REVERSAL_PATTERN"
    assert setup_pattern_type("golden_cross") == "MOVING_AVERAGE_STRUCTURE"
    assert setup_pattern_type("price_action_macd_confirmation") == (
        "PRICE_ACTION_MACD_CONFIRMATION"
    )
    assert setup_pattern_type("elliott wave") == "ELLIOTT_WAVE_PRINCIPLE"
    assert setup_pattern_type("Elliott Wave Theory") == "ELLIOTT_WAVE_PRINCIPLE"
    assert setup_pattern_type("wave principle") == "ELLIOTT_WAVE_PRINCIPLE"
    assert setup_pattern_type("support_resistance") == "SUPPORT_RESISTANCE_LEVELS"
    assert setup_pattern_type("support resistance levels") == (
        "SUPPORT_RESISTANCE_LEVELS"
    )
    assert setup_pattern_type("trend_following") == "TREND_FOLLOWING_STRUCTURE"
    assert setup_pattern_type("trend tracking") == "TREND_FOLLOWING_STRUCTURE"
    assert setup_pattern_type("trend channel") == "TREND_FOLLOWING_STRUCTURE"
    assert setup_pattern_type("butterfly") == "HARMONIC_BUTTERFLY_PATTERN"
    assert setup_pattern_type("Butterfly Pattern") == "HARMONIC_BUTTERFLY_PATTERN"
    assert setup_pattern_type("harmonic butterfly") == "HARMONIC_BUTTERFLY_PATTERN"
    assert setup_pattern_type("ascending triangle") == "BULLISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("bearish flag") == "BEARISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("bullish rectangle") == "BULLISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("bearish pennant") == "BEARISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("cup & handle") == "BULLISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("rounding bottom") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("rounding top") == "BEARISH_REVERSAL_PATTERN"
    assert setup_pattern_type("diamond bottom") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("diamond top") == "BEARISH_REVERSAL_PATTERN"
    assert setup_pattern_type("pipe bottom") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("pipe top") == "BEARISH_REVERSAL_PATTERN"
    assert setup_pattern_type("bullish staircase") is None
    assert setup_pattern_type("ascending staircase") == "BULLISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("descending staircase") == "BEARISH_CONTINUATION_PATTERN"
    assert setup_pattern_type("megaphone") == "EXPANSION_PATTERN"
    assert setup_pattern_type("quasimodo pattern") == "REVERSAL_PATTERN"
    assert setup_pattern_type("double bottom") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("head & shoulders") == "BEARISH_REVERSAL_PATTERN"
    assert setup_pattern_type("inverted H&S") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("descending wedge") == "BULLISH_REVERSAL_PATTERN"
    assert setup_pattern_type("unknown") is None


def test_compression_strategy_requires_compatible_compression_conditions() -> None:
    decision = historical_playbook_decision(
        "compression_breakout",
        candles(trending=False),
    )

    assert decision.regime is HistoricalRegime.RANGE
    assert decision.triggered is False
    assert decision.regime_strategy_reason_code == (
        "REGIME_STRATEGY_CONDITIONS_REQUIRED"
    )
    assert "VOLATILITY_COMPRESSION_INSUFFICIENT" in decision.blockers


def test_unknown_or_conflicting_regime_fails_closed() -> None:
    trend = candles(trending=True)

    unknown = historical_playbook_decision(
        "trend_continuation",
        trend,
        regime_evidence=(HistoricalRegime.UNKNOWN,),
    )
    conflict = historical_playbook_decision(
        "trend_continuation",
        trend,
        regime_evidence=(HistoricalRegime.TREND, HistoricalRegime.RANGE),
    )

    assert unknown.triggered is False
    assert unknown.blockers == ("REGIME_UNKNOWN",)
    assert unknown.regime_strategy_reason_code == "REGIME_STRATEGY_UNKNOWN"
    assert conflict.triggered is False
    assert conflict.blockers == ("REGIME_EVIDENCE_CONFLICT",)
    assert conflict.regime_strategy_reason_code == "REGIME_STRATEGY_CONFLICT"


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

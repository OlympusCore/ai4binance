"""Shared deterministic playbook identifiers and historical trigger rules."""
# ruff: noqa: E501

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from ai4binance.indicators import atr, closes, ema
from ai4binance.schemas import OHLCVCandle
from ai4binance.strategies.registry import PlaybookRegistry, build_playbook_registry

_ELLIOTT_WAVE_PATTERN_TYPE = "ELLIOTT_WAVE_PRINCIPLE"
_HARMONIC_BUTTERFLY_PATTERN_TYPE = "HARMONIC_BUTTERFLY_PATTERN"
_SUPPORT_RESISTANCE_PATTERN_TYPE = "SUPPORT_RESISTANCE_LEVELS"
_TREND_FOLLOWING_PATTERN_TYPE = "TREND_FOLLOWING_STRUCTURE"

_SETUP_ALIASES = {
    "BULLISH_BREAKOUT_RETEST": "breakout_retest",
    "BEARISH_BREAKOUT_RETEST": "breakout_retest",
    "BULLISH_SUPPORT_RECLAIM": "support_reclaim",
    "BEARISH_RESISTANCE_REJECTION": "resistance_rejection",
    "BULLISH_FAILED_BREAKOUT_REVERSAL": "failed_breakout_reversal",
    "BEARISH_FAILED_BREAKOUT_REVERSAL": "failed_breakout_reversal",
}

_SETUP_PATTERN_TYPES = {
    "trend_continuation": "CONTINUATION_PATTERN",
    "pullback_continuation": "CONTINUATION_PATTERN",
    "ascending_triangle": "BULLISH_CONTINUATION_PATTERN",
    "descending_triangle": "BEARISH_CONTINUATION_PATTERN",
    "bullish_wedge": "BULLISH_CONTINUATION_PATTERN",
    "bearish_wedge": "BEARISH_CONTINUATION_PATTERN",
    "bullish_flag": "BULLISH_CONTINUATION_PATTERN",
    "bearish_flag": "BEARISH_CONTINUATION_PATTERN",
    "bullish_rectangle": "BULLISH_CONTINUATION_PATTERN",
    "bearish_rectangle": "BEARISH_CONTINUATION_PATTERN",
    "bullish_pennant": "BULLISH_CONTINUATION_PATTERN",
    "bearish_pennant": "BEARISH_CONTINUATION_PATTERN",
    "bullish_symmetrical_triangle": "BULLISH_CONTINUATION_PATTERN",
    "bearish_symmetrical_triangle": "BEARISH_CONTINUATION_PATTERN",
    "symmetrical_triangle": "CONTINUATION_PATTERN",
    "ascending_wedge": "BEARISH_REVERSAL_PATTERN",
    "descending_wedge": "BULLISH_REVERSAL_PATTERN",
    "breakout_retest": "REVERSAL_PATTERN",
    "support_reclaim": "REVERSAL_PATTERN",
    "resistance_rejection": "REVERSAL_PATTERN",
    "failed_breakout_reversal": "REVERSAL_PATTERN",
    "compression_breakout": "BREAKOUT_PATTERN",
    "chart_pattern_breakout": "BREAKOUT_PATTERN",
    "rounding_top": "BEARISH_REVERSAL_PATTERN",
    "rounding_bottom": "BULLISH_REVERSAL_PATTERN",
    "island_reversal": "REVERSAL_PATTERN",
    "diamond_top": "BEARISH_REVERSAL_PATTERN",
    "diamond_bottom": "BULLISH_REVERSAL_PATTERN",
    "cup_and_handle": "BULLISH_CONTINUATION_PATTERN",
    "cup_handle": "BULLISH_CONTINUATION_PATTERN",
    "broadening_top": "BEARISH_REVERSAL_PATTERN",
    "broadening_bottom": "BULLISH_REVERSAL_PATTERN",
    "channel": "CONTINUATION_PATTERN",
    "pipe_top": "BEARISH_REVERSAL_PATTERN",
    "pipe_bottom": "BULLISH_REVERSAL_PATTERN",
    "spikes": "REVERSAL_PATTERN",
    "ascending_staircase": "BULLISH_CONTINUATION_PATTERN",
    "descending_staircase": "BEARISH_CONTINUATION_PATTERN",
    "megaphone": "EXPANSION_PATTERN",
    "v_pattern": "BULLISH_REVERSAL_PATTERN",
    "harmonic_pattern": "REVERSAL_PATTERN",
    # Support and resistance are structural levels, not directional reversal patterns.
    "support_resistance": _SUPPORT_RESISTANCE_PATTERN_TYPE,
    "support_resistance_levels": _SUPPORT_RESISTANCE_PATTERN_TYPE,
    "sr_levels": _SUPPORT_RESISTANCE_PATTERN_TYPE,
    # Trend following/tracking is a separate strategy family built around persistent direction.
    "trend_following": _TREND_FOLLOWING_PATTERN_TYPE,
    "trend_tracking": _TREND_FOLLOWING_PATTERN_TYPE,
    "trend_channel": _TREND_FOLLOWING_PATTERN_TYPE,
    "trend_structure": _TREND_FOLLOWING_PATTERN_TYPE,
    # Butterfly is a harmonic reversal pattern with X-A, A-B, B-C, C-D structure.
    "butterfly": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    "butterfly_pattern": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    "harmonic_butterfly": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    "harmonic_butterfly_pattern": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    "bullish_butterfly": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    "bearish_butterfly": _HARMONIC_BUTTERFLY_PATTERN_TYPE,
    # Elliott Wave is a dedicated wave-principle family, not a generic continuation pattern.
    "elliott_wave": _ELLIOTT_WAVE_PATTERN_TYPE,
    "elliott_wave_theory": _ELLIOTT_WAVE_PATTERN_TYPE,
    "elliott_wave_principle": _ELLIOTT_WAVE_PATTERN_TYPE,
    "wave_principle": _ELLIOTT_WAVE_PATTERN_TYPE,
    "wave_theory": _ELLIOTT_WAVE_PATTERN_TYPE,
    "three_drives": "REVERSAL_PATTERN",
    "bump_and_run": "REVERSAL_PATTERN",
    "quasimodo_pattern": "REVERSAL_PATTERN",
    "dead_cat_bounce": "BEARISH_REVERSAL_PATTERN",
    "scallop_pattern": "BULLISH_REVERSAL_PATTERN",
    "double_bottom": "BULLISH_REVERSAL_PATTERN",
    "triple_bottom": "BULLISH_REVERSAL_PATTERN",
    "inverted_head_and_shoulders": "BULLISH_REVERSAL_PATTERN",
    "inverted_h_s": "BULLISH_REVERSAL_PATTERN",
    "inverted_h_and_s": "BULLISH_REVERSAL_PATTERN",
    "inverse_head_and_shoulders": "BULLISH_REVERSAL_PATTERN",
    "inverse_h_s": "BULLISH_REVERSAL_PATTERN",
    "inverse_h_and_s": "BULLISH_REVERSAL_PATTERN",
    "falling_wedge": "BULLISH_REVERSAL_PATTERN",
    "double_top": "BEARISH_REVERSAL_PATTERN",
    "triple_top": "BEARISH_REVERSAL_PATTERN",
    "head_and_shoulders": "BEARISH_REVERSAL_PATTERN",
    "head_shoulders": "BEARISH_REVERSAL_PATTERN",
    "head_and_shoulders_top": "BEARISH_REVERSAL_PATTERN",
    "rising_wedge": "BEARISH_REVERSAL_PATTERN",
    "harmonic_reversal": "REVERSAL_PATTERN",
    "divergence_reversal": "REVERSAL_PATTERN",
    "smc_liquidity_sweep_reversal": "REVERSAL_PATTERN",
    "wyckoff_spring_upthrust": "REVERSAL_PATTERN",
    "candlestick_confirmation": "PRICE_ACTION_CONFIRMATION",
    "price_action_macd_confirmation": "PRICE_ACTION_MACD_CONFIRMATION",
    "session_vwap_reclaim": "VWAP_CONFIRMATION",
    "session_vwap_rejection": "VWAP_CONFIRMATION",
    "session_vwap_observation": "VWAP_CONFIRMATION",
    "golden_cross": "MOVING_AVERAGE_STRUCTURE",
    "death_cross": "MOVING_AVERAGE_STRUCTURE",
    "5_8_13": "MOVING_AVERAGE_STRUCTURE",
    "25": "MOVING_AVERAGE_STRUCTURE",
    "50": "MOVING_AVERAGE_STRUCTURE",
    "100": "MOVING_AVERAGE_STRUCTURE",
    "200": "MOVING_AVERAGE_STRUCTURE",
    "50_200": "MOVING_AVERAGE_STRUCTURE",
    "fibonacci_continuation": "FIBONACCI_RETRACEMENT",
    "fibonacci_retracement": "FIBONACCI_RETRACEMENT",
}


class HistoricalRegime(StrEnum):
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class HistoricalTriggerDecision:
    triggered: bool
    regime: HistoricalRegime
    regime_strategy_reason_code: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LevelReactionStatistics:
    level: Decimal
    touch_count: int
    successful_reactions: int
    success_rate: float
    validated: bool


@dataclass(frozen=True, slots=True)
class CompressionBreakoutEvidence:
    confirmed: bool
    resistance: Decimal
    current_atr: Decimal
    compression_ratio: Decimal
    volume_ratio: Decimal
    reaction_count: int
    blockers: tuple[str, ...]


def level_reaction_statistics(
    history: tuple[OHLCVCandle, ...],
    level: Decimal,
    *,
    support: bool,
) -> LevelReactionStatistics:
    """Validate a structural level from causal touch/reaction observations."""
    sample = history[-42:-2]
    if len(sample) < 15:
        return LevelReactionStatistics(level, 0, 0, 0.0, False)
    tolerance = atr(sample, 14) * Decimal("0.25")
    touches = 0
    successes = 0
    for current, following in pairwise(sample):
        touched = current.low <= level + tolerance and current.high >= level - tolerance
        if not touched:
            continue
        touches += 1
        reacted = (
            following.close >= level + tolerance
            if support
            else following.close <= level - tolerance
        )
        successes += reacted
    rate = successes / touches if touches else 0.0
    return LevelReactionStatistics(
        level,
        touches,
        successes,
        rate,
        touches >= 2 and rate >= 0.6,
    )


REGIME_STRATEGY_ELIGIBLE = "REGIME_STRATEGY_ELIGIBLE"
REGIME_STRATEGY_INCOMPATIBLE = "REGIME_STRATEGY_INCOMPATIBLE"
REGIME_STRATEGY_UNKNOWN = "REGIME_STRATEGY_UNKNOWN"
REGIME_STRATEGY_CONFLICT = "REGIME_STRATEGY_CONFLICT"
REGIME_STRATEGY_CONDITIONS_REQUIRED = "REGIME_STRATEGY_CONDITIONS_REQUIRED"


def canonical_setup_name(value: str) -> str | None:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered in {
        "pullback_continuation",
        "breakout_retest",
        "support_reclaim",
        "resistance_rejection",
        "failed_breakout_reversal",
        "compression_breakout",
    }:
        return lowered
    return _SETUP_ALIASES.get(normalized.upper())


def setup_pattern_type(value: str) -> str | None:
    """Return the governed pattern family for a canonical or raw setup label."""

    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        return None
    canonical = canonical_setup_name(value)
    if canonical is not None:
        normalized = canonical
    return _SETUP_PATTERN_TYPES.get(normalized)


def historical_playbook_trigger(
    playbook: str,
    history: tuple[OHLCVCandle, ...],
) -> bool:
    """Evaluate closed-candle rules shared by validation adapters."""
    return historical_playbook_decision(playbook, history).triggered


def historical_playbook_decision(
    playbook: str,
    history: tuple[OHLCVCandle, ...],
    *,
    registry: PlaybookRegistry | None = None,
    regime_evidence: tuple[HistoricalRegime, ...] = (),
) -> HistoricalTriggerDecision:
    """Return a causal trigger decision with explicit regime/quality blockers."""
    if len(history) < 22:
        return HistoricalTriggerDecision(
            False,
            HistoricalRegime.RANGE,
            REGIME_STRATEGY_CONDITIONS_REQUIRED,
            ("INSUFFICIENT_PLAYBOOK_HISTORY",),
        )
    registry = registry or build_playbook_registry()
    recent = history[-50:]
    fast = ema(closes(recent), 8)
    slow = ema(closes(recent), 21)
    current, previous = recent[-1], recent[-2]
    prior = recent[-12:-2]
    current_atr = atr(recent, 14)
    volatility_ratio = current_atr / current.close
    ema_separation = abs(fast - slow) / current.close
    regime = (
        HistoricalRegime.HIGH_VOLATILITY
        if volatility_ratio >= Decimal("0.04")
        else HistoricalRegime.TREND
        if ema_separation >= Decimal("0.01")
        else HistoricalRegime.RANGE
    )
    resolved_regime, regime_blockers, regime_reason = _resolve_regime_evidence(
        detected_regime=regime,
        regime_evidence=regime_evidence,
    )
    if regime_blockers:
        return HistoricalTriggerDecision(
            False,
            resolved_regime,
            regime_reason,
            regime_blockers,
        )
    allowed = _allowed_regimes(playbook, registry)
    if resolved_regime not in allowed:
        return HistoricalTriggerDecision(
            False,
            resolved_regime,
            REGIME_STRATEGY_INCOMPATIBLE,
            (f"REGIME_BLOCKED:{resolved_regime.value}",),
        )
    if playbook == "compression_breakout":
        evidence = compression_breakout_evidence(history)
        reason_code = (
            REGIME_STRATEGY_ELIGIBLE
            if evidence.confirmed
            else REGIME_STRATEGY_CONDITIONS_REQUIRED
        )
        return HistoricalTriggerDecision(
            evidence.confirmed,
            resolved_regime,
            reason_code,
            evidence.blockers,
        )
    average_volume = sum((item.volume for item in recent[-21:-1]), Decimal("0")) / 20
    volume_ratio = (
        current.volume / average_volume if average_volume > 0 else Decimal("0")
    )
    candle_range = current.high - current.low
    body_ratio = (
        abs(current.close - current.open) / candle_range
        if candle_range > 0
        else Decimal("0")
    )
    quality_blockers: list[str] = []
    if volume_ratio < Decimal("1.05"):
        quality_blockers.append("RELATIVE_VOLUME_INSUFFICIENT")
    if playbook in {"breakout_retest", "support_reclaim"} and body_ratio < Decimal(
        "0.35"
    ):
        quality_blockers.append("CANDLE_BODY_QUALITY_INSUFFICIENT")
    if quality_blockers:
        return HistoricalTriggerDecision(
            False,
            resolved_regime,
            REGIME_STRATEGY_CONDITIONS_REQUIRED,
            tuple(quality_blockers),
        )
    if playbook == "trend_continuation":
        triggered = (
            fast > slow and current.close > fast and current.close > previous.close
        )
    elif playbook == "pullback_continuation":
        triggered = fast > slow and previous.close <= fast < current.close
    elif playbook == "breakout_retest":
        resistance = max(candle.high for candle in prior)
        reactions = level_reaction_statistics(history, resistance, support=False)
        if not reactions.validated:
            return HistoricalTriggerDecision(
                False,
                resolved_regime,
                REGIME_STRATEGY_CONDITIONS_REQUIRED,
                ("LEVEL_REACTION_EVIDENCE_INSUFFICIENT",),
            )
        triggered = (
            previous.close > resistance and current.low <= resistance < current.close
        )
    elif playbook == "support_reclaim":
        support = min(candle.low for candle in prior)
        reactions = level_reaction_statistics(history, support, support=True)
        if not reactions.validated:
            return HistoricalTriggerDecision(
                False,
                resolved_regime,
                REGIME_STRATEGY_CONDITIONS_REQUIRED,
                ("LEVEL_REACTION_EVIDENCE_INSUFFICIENT",),
            )
        reclaim_quality = current.close >= current.low + candle_range * Decimal("0.6")
        triggered = current.low < support < current.close and reclaim_quality
    elif playbook == "failed_breakout_reversal":
        support = min(candle.low for candle in prior)
        triggered = previous.close < support and current.close > support
    else:
        triggered = False
    return HistoricalTriggerDecision(
        triggered,
        resolved_regime,
        REGIME_STRATEGY_ELIGIBLE if triggered else REGIME_STRATEGY_CONDITIONS_REQUIRED,
        () if triggered else ("PLAYBOOK_GEOMETRY_NOT_CONFIRMED",),
    )


def _allowed_regimes(
    playbook: str,
    registry: PlaybookRegistry,
) -> frozenset[HistoricalRegime]:
    try:
        compatible = registry.get(playbook).compatible_regimes
    except KeyError:
        return frozenset()
    if compatible == ("ALL_VALIDATED_REGIMES",):
        return frozenset(
            {
                HistoricalRegime.TREND,
                HistoricalRegime.RANGE,
                HistoricalRegime.HIGH_VOLATILITY,
            }
        )
    return frozenset(HistoricalRegime(item) for item in compatible)


def _resolve_regime_evidence(
    *,
    detected_regime: HistoricalRegime,
    regime_evidence: tuple[HistoricalRegime, ...],
) -> tuple[HistoricalRegime, tuple[str, ...], str]:
    if not regime_evidence:
        return detected_regime, (), REGIME_STRATEGY_ELIGIBLE
    unique = frozenset(regime_evidence)
    if HistoricalRegime.UNKNOWN in unique:
        return (
            HistoricalRegime.UNKNOWN,
            ("REGIME_UNKNOWN",),
            REGIME_STRATEGY_UNKNOWN,
        )
    if len(unique) > 1:
        return (
            detected_regime,
            ("REGIME_EVIDENCE_CONFLICT",),
            REGIME_STRATEGY_CONFLICT,
        )
    resolved = next(iter(unique))
    if resolved is not detected_regime:
        return (
            detected_regime,
            ("REGIME_EVIDENCE_CONFLICT",),
            REGIME_STRATEGY_CONFLICT,
        )
    return resolved, (), REGIME_STRATEGY_ELIGIBLE


def compression_breakout_evidence(
    history: tuple[OHLCVCandle, ...],
) -> CompressionBreakoutEvidence:
    """Require contraction, closed-candle breakout, retest and prior reactions."""
    if len(history) < 34:
        return CompressionBreakoutEvidence(
            False,
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
            Decimal("0"),
            0,
            ("INSUFFICIENT_COMPRESSION_HISTORY",),
        )
    recent = history[-34:]
    baseline = recent[-32:-12]
    compressed = recent[-10:-2]
    breakout = recent[-2]
    retest = recent[-1]
    current_atr = atr(recent, 14)
    baseline_range = sum(
        (item.high - item.low for item in baseline), Decimal("0")
    ) / Decimal(len(baseline))
    compressed_range = sum(
        (item.high - item.low for item in compressed), Decimal("0")
    ) / Decimal(len(compressed))
    compression_ratio = (
        compressed_range / baseline_range if baseline_range > 0 else Decimal("1")
    )
    resistance = max(item.high for item in baseline)
    tolerance = current_atr * Decimal("0.25")
    reactions = sum(abs(item.high - resistance) <= tolerance for item in baseline)
    average_volume = sum(
        (item.volume for item in recent[-22:-2]), Decimal("0")
    ) / Decimal("20")
    volume_ratio = (
        breakout.volume / average_volume if average_volume > 0 else Decimal("0")
    )
    candle_range = breakout.high - breakout.low
    body_ratio = (
        abs(breakout.close - breakout.open) / candle_range
        if candle_range > 0
        else Decimal("0")
    )
    blockers: list[str] = []
    if compression_ratio > Decimal("0.70"):
        blockers.append("VOLATILITY_COMPRESSION_INSUFFICIENT")
    if reactions < 2:
        blockers.append("LEVEL_REACTION_EVIDENCE_INSUFFICIENT")
    if volume_ratio < Decimal("1.20"):
        blockers.append("BREAKOUT_VOLUME_EXPANSION_INSUFFICIENT")
    if body_ratio < Decimal("0.35"):
        blockers.append("BREAKOUT_BODY_QUALITY_INSUFFICIENT")
    if breakout.close <= resistance:
        blockers.append("COMPRESSION_BREAKOUT_NOT_CONFIRMED")
    if not (retest.low <= resistance < retest.close):
        blockers.append("COMPRESSION_RETEST_NOT_CONFIRMED")
    return CompressionBreakoutEvidence(
        not blockers,
        resistance,
        current_atr,
        compression_ratio,
        volume_ratio,
        reactions,
        tuple(blockers),
    )

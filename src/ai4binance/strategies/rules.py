"""Shared deterministic playbook identifiers and historical trigger rules."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from ai4binance.indicators import atr, closes, ema
from ai4binance.schemas import OHLCVCandle

_SETUP_ALIASES = {
    "BULLISH_BREAKOUT_RETEST": "breakout_retest",
    "BEARISH_BREAKOUT_RETEST": "breakout_retest",
    "BULLISH_SUPPORT_RECLAIM": "support_reclaim",
    "BEARISH_RESISTANCE_REJECTION": "resistance_rejection",
    "BULLISH_FAILED_BREAKOUT_REVERSAL": "failed_breakout_reversal",
    "BEARISH_FAILED_BREAKOUT_REVERSAL": "failed_breakout_reversal",
}


class HistoricalRegime(StrEnum):
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


@dataclass(frozen=True, slots=True)
class HistoricalTriggerDecision:
    triggered: bool
    regime: HistoricalRegime
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


_ALLOWED_REGIMES = {
    "trend_continuation": frozenset({HistoricalRegime.TREND}),
    "pullback_continuation": frozenset({HistoricalRegime.TREND}),
    "breakout_retest": frozenset(
        {HistoricalRegime.TREND, HistoricalRegime.HIGH_VOLATILITY}
    ),
    "support_reclaim": frozenset({HistoricalRegime.TREND, HistoricalRegime.RANGE}),
    "failed_breakout_reversal": frozenset(
        {HistoricalRegime.RANGE, HistoricalRegime.HIGH_VOLATILITY}
    ),
    "compression_breakout": frozenset(
        {HistoricalRegime.RANGE, HistoricalRegime.HIGH_VOLATILITY}
    ),
}


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


def historical_playbook_trigger(
    playbook: str,
    history: tuple[OHLCVCandle, ...],
) -> bool:
    """Evaluate closed-candle rules shared by validation adapters."""
    return historical_playbook_decision(playbook, history).triggered


def historical_playbook_decision(
    playbook: str,
    history: tuple[OHLCVCandle, ...],
) -> HistoricalTriggerDecision:
    """Return a causal trigger decision with explicit regime/quality blockers."""
    if len(history) < 22:
        return HistoricalTriggerDecision(
            False,
            HistoricalRegime.RANGE,
            ("INSUFFICIENT_PLAYBOOK_HISTORY",),
        )
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
    allowed = _ALLOWED_REGIMES.get(playbook, frozenset())
    if regime not in allowed:
        return HistoricalTriggerDecision(
            False,
            regime,
            (f"REGIME_BLOCKED:{regime.value}",),
        )
    if playbook == "compression_breakout":
        evidence = compression_breakout_evidence(history)
        return HistoricalTriggerDecision(
            evidence.confirmed,
            regime,
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
        return HistoricalTriggerDecision(False, regime, tuple(quality_blockers))
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
                regime,
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
                regime,
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
        regime,
        () if triggered else ("PLAYBOOK_GEOMETRY_NOT_CONFIRMED",),
    )


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

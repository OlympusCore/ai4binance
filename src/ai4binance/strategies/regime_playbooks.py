"""Deterministic research engines for three regime-specific Spot playbooks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.indicators import atr
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    OHLCVCandle,
    is_usable_agent_result,
)


@dataclass(frozen=True, slots=True)
class PlaybookEvidence:
    setup_name: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    atr: Decimal
    evidence: tuple[str, ...]


def range_rotation_evidence(
    candles: tuple[OHLCVCandle, ...],
) -> PlaybookEvidence | None:
    if len(candles) < 31:
        return None
    baseline = candles[-21:-1]
    latest = candles[-1]
    current_atr = atr(candles, 14)
    range_low = min(item.low for item in baseline)
    range_high = max(item.high for item in baseline)
    width = range_high - range_low
    if width < current_atr * Decimal("2"):
        return None
    lower_quartile = range_low + width * Decimal("0.25")
    drift = abs(baseline[-1].close - baseline[0].close)
    if (
        drift > width * Decimal("0.35")
        or latest.low > lower_quartile
        or latest.close <= latest.open
        or latest.close > lower_quartile
    ):
        return None
    stop = range_low - current_atr * Decimal("0.25")
    target = range_low + width * Decimal("0.50")
    if stop <= 0 or target <= latest.close:
        return None
    return PlaybookEvidence(
        "range_rotation",
        latest.close,
        stop,
        target,
        current_atr,
        ("RANGE_WIDTH_VALID", "LOWER_QUARTILE_RECLAIM", "RANGE_DRIFT_BOUNDED"),
    )


def volatility_expansion_evidence(
    candles: tuple[OHLCVCandle, ...],
) -> PlaybookEvidence | None:
    if len(candles) < 31:
        return None
    previous = candles[-21:-1]
    latest = candles[-1]
    ranges = sorted(item.high - item.low for item in previous)
    median_range = (ranges[9] + ranges[10]) / 2
    average_volume = sum((item.volume for item in previous), Decimal("0")) / 20
    latest_range = latest.high - latest.low
    current_atr = atr(candles, 14)
    closes_near_high = latest.close >= latest.low + latest_range * Decimal("0.75")
    if (
        median_range <= 0
        or latest_range < median_range * Decimal("1.8")
        or latest.volume < average_volume * Decimal("1.5")
        or latest.close <= max(item.high for item in previous)
        or not closes_near_high
    ):
        return None
    stop = latest.close - current_atr * Decimal("1.5")
    target = latest.close + current_atr * Decimal("3")
    if stop <= 0:
        return None
    return PlaybookEvidence(
        "volatility_expansion",
        latest.close,
        stop,
        target,
        current_atr,
        ("TRUE_RANGE_EXPANSION", "VOLUME_EXPANSION", "CLOSE_NEAR_HIGH"),
    )


def liquidity_sweep_reversal_evidence(
    candles: tuple[OHLCVCandle, ...],
) -> PlaybookEvidence | None:
    if len(candles) < 32:
        return None
    history = candles[-22:-2]
    sweep, confirmation = candles[-2], candles[-1]
    support = min(item.low for item in history)
    sweep_body_low = min(sweep.open, sweep.close)
    lower_wick = sweep_body_low - sweep.low
    body = abs(sweep.close - sweep.open)
    current_atr = atr(candles, 14)
    if (
        sweep.low >= support
        or sweep.close <= support
        or lower_wick < max(body, current_atr * Decimal("0.35"))
        or confirmation.close <= sweep.high
        or confirmation.close <= confirmation.open
    ):
        return None
    stop = sweep.low - current_atr * Decimal("0.20")
    risk = confirmation.close - stop
    target = confirmation.close + risk * Decimal("2")
    if stop <= 0 or risk <= 0:
        return None
    return PlaybookEvidence(
        "smc_liquidity_sweep_reversal",
        confirmation.close,
        stop,
        target,
        current_atr,
        ("SUPPORT_LIQUIDITY_SWEEP", "LEVEL_RECLAIM", "FOLLOW_THROUGH_CONFIRMED"),
    )


@dataclass(frozen=True, slots=True)
class RegimePlaybookEngine:
    """Generate research candidates without owning final decisions."""

    def generate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        *,
        timeframe: str | None = None,
    ) -> tuple[TradeCandidate, ...]:
        if snapshot.latest_price is None:
            return ()
        required = tuple(
            agent_results.get(name)
            for name in ("market_structure", "volatility", "confluence")
        )
        if any(item is None or not is_usable_agent_result(item) for item in required):
            return ()
        timeframe = timeframe or (
            "1h" if "1h" in snapshot.timeframes else snapshot.timeframes[0]
        )
        if timeframe not in snapshot.timeframes:
            raise ValueError("playbook timeframe is absent from snapshot")
        candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
        evidence_items = tuple(
            item
            for item in (
                range_rotation_evidence(candles),
                volatility_expansion_evidence(candles),
                liquidity_sweep_reversal_evidence(candles),
            )
            if item is not None
        )
        confluence = agent_results["confluence"]
        return tuple(
            self._candidate(snapshot, timeframe, item, confluence)
            for item in evidence_items
        )

    @staticmethod
    def _candidate(
        snapshot: MarketSnapshot,
        timeframe: str,
        evidence: PlaybookEvidence,
        confluence: AgentResult,
    ) -> TradeCandidate:
        risk = evidence.entry - evidence.stop
        zone = evidence.atr * Decimal("0.05")
        identity = f"{snapshot.snapshot_id}|{timeframe}|{evidence.setup_name}|BUY"
        return TradeCandidate(
            candidate_id=f"candidate:{sha256(identity.encode()).hexdigest()[:16]}",
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            action=Action.BUY,
            setup_name=evidence.setup_name,
            status=CandidateStatus.READY_FOR_RISK,
            entry_zone=PriceZone(evidence.entry - zone, evidence.entry + zone),
            invalidation_level=evidence.stop,
            stop_loss=evidence.stop,
            take_profit_levels=(evidence.target,),
            trailing_stop=evidence.stop,
            atr=evidence.atr,
            risk_reward=(evidence.target - evidence.entry) / risk,
            score=confluence.score,
            confidence=confluence.confidence,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
            evidence=evidence.evidence,
        )

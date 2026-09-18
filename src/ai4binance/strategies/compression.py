"""Research-only compression breakout and retest candidate generation."""

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
from ai4binance.schemas import AgentResult, MarketSnapshot, is_usable_agent_result
from ai4binance.strategies.rules import compression_breakout_evidence


@dataclass(frozen=True, slots=True)
class CompressionBreakoutPlaybookEngine:
    """Create a Spot-long candidate only after contraction-breakout-retest."""

    target_risk_multiple: Decimal = Decimal("2")

    def generate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        *,
        timeframe: str | None = None,
    ) -> tuple[TradeCandidate, ...]:
        required_names = ("volatility", "volume", "multi_timeframe", "confluence")
        required = tuple(agent_results.get(name) for name in required_names)
        if snapshot.latest_price is None or any(item is None for item in required):
            return ()
        if any(item is None or not is_usable_agent_result(item) for item in required):
            return ()
        timeframe = timeframe or (
            "1h" if "1h" in snapshot.timeframes else snapshot.timeframes[0]
        )
        if timeframe not in snapshot.timeframes:
            raise ValueError("playbook timeframe is absent from snapshot")
        candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
        evidence = compression_breakout_evidence(candles)
        if not evidence.confirmed:
            return ()
        entry = snapshot.latest_price
        stop = min(
            candles[-1].low - evidence.current_atr * Decimal("0.10"),
            evidence.resistance - evidence.current_atr * Decimal("0.25"),
        )
        if stop <= 0 or stop >= entry:
            return ()
        risk = entry - stop
        target = entry + risk * self.target_risk_multiple
        zone_width = evidence.current_atr * Decimal("0.10")
        confluence = agent_results["confluence"]
        candidate = TradeCandidate(
            candidate_id=self._candidate_id(snapshot.snapshot_id, timeframe),
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            action=Action.BUY,
            setup_name="compression_breakout",
            status=CandidateStatus.READY_FOR_RISK,
            entry_zone=PriceZone(entry - zone_width, entry + zone_width),
            invalidation_level=stop,
            stop_loss=stop,
            take_profit_levels=(target,),
            trailing_stop=stop,
            atr=evidence.current_atr,
            risk_reward=self.target_risk_multiple,
            score=confluence.score,
            confidence=confluence.confidence,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
            evidence=(
                "VOLATILITY_COMPRESSION_CONFIRMED",
                "CLOSED_CANDLE_BREAKOUT_CONFIRMED",
                "BREAKOUT_RETEST_CONFIRMED",
                f"REACTION_COUNT:{evidence.reaction_count}",
                f"VOLUME_RATIO:{evidence.volume_ratio}",
            ),
            blockers=(),
        )
        return (candidate,)

    @staticmethod
    def _candidate_id(snapshot_id: str, timeframe: str) -> str:
        payload = f"{snapshot_id}|compression_breakout|{timeframe}"
        return f"candidate:{sha256(payload.encode('utf-8')).hexdigest()[:16]}"

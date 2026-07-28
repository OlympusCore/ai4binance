"""Deterministic governed price-action playbook candidate generation."""

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
from ai4binance.schemas import AgentResult, MarketSnapshot, is_usable_agent_result
from ai4binance.strategies.rules import canonical_setup_name

SUPPORTED_SETUPS = (
    "pullback_continuation",
    "breakout_retest",
    "support_reclaim",
    "resistance_rejection",
    "failed_breakout_reversal",
)


@dataclass(frozen=True, slots=True)
class PriceActionPlaybookEngine:
    """Translate validated setup codes into research-only Spot candidates."""

    atr_multiplier: Decimal = Decimal("1.5")
    target_multiplier: Decimal = Decimal("3.0")

    def generate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[TradeCandidate, ...]:
        required_names = (
            "trend",
            "market_structure",
            "multi_timeframe",
            "confluence",
        )
        if snapshot.latest_price is None or any(
            name not in agent_results for name in required_names
        ):
            return ()
        required = tuple(agent_results[name] for name in required_names)
        if any(not is_usable_agent_result(item) for item in required):
            return ()
        setup_sources: dict[str, AgentResult] = {}
        for result in agent_results.values():
            if not is_usable_agent_result(result):
                continue
            for detected in result.detected_setups:
                canonical = canonical_setup_name(detected)
                if canonical in SUPPORTED_SETUPS:
                    setup_sources.setdefault(canonical, result)
        setups = tuple(setup for setup in SUPPORTED_SETUPS if setup in setup_sources)
        if not setups:
            return ()
        timeframe = "1h" if "1h" in snapshot.timeframes else snapshot.timeframes[0]
        candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
        if len(candles) < 15:
            return ()
        current_atr = atr(candles, 14)
        entry = snapshot.latest_price
        if current_atr <= 0 or entry <= current_atr * self.atr_multiplier:
            return ()
        return tuple(
            candidate
            for setup in setups
            if (
                candidate := self._candidate(
                    setup,
                    snapshot,
                    agent_results,
                    timeframe,
                    entry,
                    current_atr,
                    setup_sources[setup],
                )
            )
            is not None
        )

    def _candidate(
        self,
        setup: str,
        snapshot: MarketSnapshot,
        results: Mapping[str, AgentResult],
        timeframe: str,
        entry: Decimal,
        current_atr: Decimal,
        setup_source: AgentResult,
    ) -> TradeCandidate | None:
        direction = setup_source.directional_vote
        if setup in {"pullback_continuation", "breakout_retest"}:
            trend_direction = (
                results["trend"].directional_vote
                + results["market_structure"].directional_vote
                + results["multi_timeframe"].directional_vote
            ) / 3
            if direction * trend_direction <= 0 or abs(trend_direction) < 0.2:
                return None
        if abs(direction) < 0.2:
            return None
        action = Action.BUY if direction > 0 else Action.SELL
        if setup == "support_reclaim" and action is not Action.BUY:
            return None
        if setup == "resistance_rejection" and action is not Action.SELL:
            return None
        stop_distance = current_atr * self.atr_multiplier
        target_distance = current_atr * self.target_multiplier
        if action is Action.BUY:
            stop = entry - stop_distance
            target = entry + target_distance
        else:
            stop = entry + stop_distance
            target = entry - target_distance
            if target <= 0:
                return None
        blockers: list[str] = []
        inventory_action = "NONE"
        status = CandidateStatus.READY_FOR_RISK
        if action is Action.SELL:
            inventory_action = "REDUCE_EXISTING_SPOT_INVENTORY"
            if not snapshot.inventory_summary:
                blockers.append("INVENTORY_UNKNOWN_FOR_SPOT_SELL")
                status = CandidateStatus.RESEARCH_ONLY
        zone_width = current_atr * Decimal("0.10")
        confluence = results["confluence"]
        if (
            abs(confluence.directional_vote) >= 0.15
            and confluence.directional_vote * direction <= 0
        ):
            return None
        return TradeCandidate(
            candidate_id=self._candidate_id(snapshot.snapshot_id, setup, action),
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            action=action,
            setup_name=setup,
            status=status,
            entry_zone=PriceZone(entry - zone_width, entry + zone_width),
            invalidation_level=stop,
            stop_loss=stop,
            take_profit_levels=(target,),
            trailing_stop=stop,
            atr=current_atr,
            risk_reward=target_distance / stop_distance,
            score=confluence.score,
            confidence=confluence.confidence,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
            inventory_action=inventory_action,
            evidence=(
                f"PLAYBOOK_{setup.upper()}",
                *setup_source.evidence,
            ),
            blockers=tuple(blockers),
        )

    @staticmethod
    def _candidate_id(snapshot_id: str, setup: str, action: Action) -> str:
        payload = f"{snapshot_id}|{setup}|{action.value}"
        return f"candidate:{sha256(payload.encode('utf-8')).hexdigest()[:16]}"

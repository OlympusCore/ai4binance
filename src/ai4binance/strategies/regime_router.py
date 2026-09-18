"""Deterministic regime router for bounded virtual-market candidate routing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from ai4binance.domain import Action, CandidateStatus, TradeCandidate
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    is_futures_market_type,
    is_usable_agent_result,
)

ZERO = Decimal("0")


class RoutedMarketRegime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RegimeRoutingDecision:
    regime: RoutedMarketRegime
    allowed_strategy_ids: tuple[str, ...]
    allowed_actions: tuple[Action, ...]
    reduced_risk: bool = False
    wait_reason: str | None = None
    spot_defensive_cash: bool = False


@dataclass(frozen=True, slots=True)
class DeterministicRegimeRouter:
    """Classify market regime and route candidates without execution authority."""

    def decide(
        self,
        agent_results: Mapping[str, AgentResult],
    ) -> RegimeRoutingDecision:
        result = agent_results.get("market_regime")
        regime = self._classify(result)
        if regime is RoutedMarketRegime.TREND_UP:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=(
                    "TREND_PULLBACK",
                    "BREAKOUT_RETEST",
                    "MOMENTUM_CONTINUATION",
                ),
                allowed_actions=(Action.BUY,),
            )
        if regime is RoutedMarketRegime.TREND_DOWN:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=("BREAKOUT_RETEST", "MOMENTUM_CONTINUATION"),
                allowed_actions=(Action.SELL,),
                spot_defensive_cash=True,
            )
        if regime is RoutedMarketRegime.RANGE:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=("MEAN_REVERSION",),
                allowed_actions=(Action.BUY, Action.SELL),
            )
        if regime is RoutedMarketRegime.HIGH_VOLATILITY:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=("BREAKOUT_RETEST",),
                allowed_actions=(Action.BUY, Action.SELL),
                reduced_risk=True,
            )
        if regime is RoutedMarketRegime.LOW_VOLATILITY:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=(),
                allowed_actions=(),
                wait_reason="REGIME_ROUTE_WAIT_LOW_VOLATILITY",
            )
        if regime is RoutedMarketRegime.TRANSITION:
            return RegimeRoutingDecision(
                regime=regime,
                allowed_strategy_ids=(),
                allowed_actions=(),
                wait_reason="REGIME_ROUTE_WAIT_TRANSITION",
            )
        return RegimeRoutingDecision(
            regime=RoutedMarketRegime.UNKNOWN,
            allowed_strategy_ids=(),
            allowed_actions=(),
            wait_reason="REGIME_ROUTE_WAIT_UNKNOWN",
        )

    def route_candidate(
        self,
        snapshot: MarketSnapshot,
        candidate: TradeCandidate,
        *,
        strategy_id: str,
        decision: RegimeRoutingDecision,
    ) -> TradeCandidate:
        evidence = [
            *candidate.evidence,
            f"REGIME_ROUTE:{decision.regime.value}",
        ]
        if decision.reduced_risk:
            evidence.append("REGIME_ROUTE_RISK:REDUCED_RISK")
        blockers = list(candidate.blockers)
        status = candidate.status

        market = self._market_surface(snapshot)
        if decision.wait_reason is not None:
            blockers.append(decision.wait_reason)
            status = CandidateStatus.WAIT_FOR_RETEST
        elif decision.spot_defensive_cash and market == "SPOT":
            blockers.append("REGIME_ROUTE_SPOT_DEFENSIVE_CASH")
            status = CandidateStatus.RESEARCH_ONLY
        elif strategy_id not in decision.allowed_strategy_ids:
            blockers.append(f"REGIME_ROUTE_STRATEGY_BLOCKED:{decision.regime.value}")
            status = CandidateStatus.WAIT_FOR_RETEST
        elif candidate.action not in decision.allowed_actions:
            blockers.append(
                f"REGIME_ROUTE_ACTION_BLOCKED:{decision.regime.value}:{candidate.action.value}"
            )
            status = CandidateStatus.WAIT_FOR_RETEST

        unique_blockers = tuple(dict.fromkeys(blockers))
        unique_evidence = tuple(dict.fromkeys(evidence))
        return TradeCandidate(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            timestamp=candidate.timestamp,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            action=candidate.action,
            setup_name=candidate.setup_name,
            status=status,
            entry_zone=candidate.entry_zone,
            invalidation_level=candidate.invalidation_level,
            stop_loss=candidate.stop_loss,
            take_profit_levels=candidate.take_profit_levels,
            trailing_stop=candidate.trailing_stop,
            atr=candidate.atr,
            risk_reward=candidate.risk_reward,
            score=candidate.score,
            confidence=candidate.confidence,
            ranking_score=candidate.ranking_score,
            promotion_status=candidate.promotion_status,
            inventory_action=candidate.inventory_action,
            market_type=candidate.market_type,
            evidence=unique_evidence,
            blockers=unique_blockers,
        )

    def _classify(self, result: AgentResult | None) -> RoutedMarketRegime:
        if result is None or not is_usable_agent_result(result):
            return RoutedMarketRegime.UNKNOWN
        raw = self._string_metadata(result, "regime")
        if raw in {"STRONG_UPTREND", "WEAK_UPTREND"}:
            return RoutedMarketRegime.TREND_UP
        if raw in {"STRONG_DOWNTREND", "WEAK_DOWNTREND"}:
            return RoutedMarketRegime.TREND_DOWN
        if raw == "RANGE":
            return RoutedMarketRegime.RANGE
        if raw == "ABNORMAL_MARKET":
            return RoutedMarketRegime.HIGH_VOLATILITY
        if raw == "COMPRESSION":
            return RoutedMarketRegime.LOW_VOLATILITY
        atr_ratio = self._decimal_metadata(result, "atr_ratio")
        if (
            atr_ratio is not None
            and atr_ratio > ZERO
            and abs(result.directional_vote) < 0.2
        ):
            return RoutedMarketRegime.TRANSITION
        return RoutedMarketRegime.UNKNOWN

    @staticmethod
    def _market_surface(snapshot: MarketSnapshot) -> str:
        return (
            "USD_M_FUTURES" if is_futures_market_type(snapshot.market_type) else "SPOT"
        )

    @staticmethod
    def _string_metadata(result: AgentResult, key: str) -> str | None:
        value = result.calculation_metadata.get(key)
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _decimal_metadata(result: AgentResult, key: str) -> Decimal | None:
        value = result.calculation_metadata.get(key)
        if value is None or isinstance(value, bool):
            return None
        if not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() and parsed >= ZERO else None

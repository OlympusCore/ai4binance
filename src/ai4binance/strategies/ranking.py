"""Deterministic virtual-market candidate ranking for autonomous simulation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from math import isfinite

from ai4binance.domain import Action, CandidateStatus, TradeCandidate
from ai4binance.risk import RiskConfig
from ai4binance.schemas import AgentResult, MarketSnapshot, is_usable_agent_result
from ai4binance.strategies.registry import PlaybookRegistry, build_playbook_registry

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class VirtualMarketCandidateRanker:
    """Rank blocker-free simulation candidates without changing veto authority."""

    registry: PlaybookRegistry = field(default_factory=build_playbook_registry)
    max_candidates: int = 5
    risk_config: RiskConfig = field(default_factory=RiskConfig)

    def __post_init__(self) -> None:
        if not 1 <= self.max_candidates <= 5:
            raise ValueError("max_candidates must be between one and five")

    def rank(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        candidates: tuple[TradeCandidate, ...],
    ) -> tuple[TradeCandidate, ...]:
        """Return up to five deterministically ordered candidates for simulation."""

        eligible: list[TradeCandidate] = []
        ineligible: list[TradeCandidate] = []
        for candidate in candidates:
            normalized = replace(candidate, ranking_score=None)
            if self._is_rank_eligible(normalized):
                eligible.append(
                    replace(
                        normalized,
                        ranking_score=round(
                            self._ranking_score(snapshot, agent_results, normalized),
                            6,
                        ),
                    )
                )
            else:
                ineligible.append(normalized)

        eligible.sort(
            key=lambda item: (
                -(item.ranking_score or 0.0),
                -item.score,
                -item.confidence,
                -item.risk_reward,
                item.candidate_id,
            )
        )
        ineligible.sort(
            key=lambda item: (
                0 if item.status is CandidateStatus.READY_FOR_RISK else 1,
                len(item.blockers),
                -item.score,
                -item.confidence,
                -item.risk_reward,
                item.candidate_id,
            )
        )
        return tuple((*eligible, *ineligible)[: self.max_candidates])

    @staticmethod
    def _is_rank_eligible(candidate: TradeCandidate) -> bool:
        return (
            candidate.status is CandidateStatus.READY_FOR_RISK
            and not candidate.blockers
        )

    def _ranking_score(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        candidate: TradeCandidate,
    ) -> float:
        action_sign = 1.0 if candidate.action is Action.BUY else -1.0
        setup_quality = (candidate.score * 0.40) + (candidate.confidence * 10.0)
        regime_fit = self._regime_fit(agent_results, candidate)
        mtf_alignment = self._mtf_alignment(agent_results, action_sign)
        liquidity_quality = self._liquidity_quality(snapshot, agent_results)
        execution_cost = self._execution_cost_quality(snapshot)
        risk_reward = self._risk_reward_quality(candidate)
        historical_edge = self._historical_edge_bonus(agent_results, candidate)
        portfolio_penalty = self._portfolio_penalty(snapshot, candidate)
        total = (
            setup_quality
            + regime_fit
            + mtf_alignment
            + liquidity_quality
            + execution_cost
            + risk_reward
            + historical_edge
            - portfolio_penalty
        )
        return float(max(0.0, min(100.0, total)))

    def _regime_fit(
        self,
        agent_results: Mapping[str, AgentResult],
        candidate: TradeCandidate,
    ) -> float:
        result = agent_results.get("market_regime")
        regime = self._string_metadata(result, "regime")
        if regime is None:
            return 0.0
        compatible = self.registry.get(candidate.setup_name).compatible_regimes
        if compatible == ("ALL_VALIDATED_REGIMES",):
            return 12.0
        return 15.0 if regime in compatible else 0.0

    @staticmethod
    def _mtf_alignment(
        agent_results: Mapping[str, AgentResult],
        action_sign: float,
    ) -> float:
        result = agent_results.get("multi_timeframe")
        if result is None or not is_usable_agent_result(result):
            return 0.0
        alignment = max(0.0, min(1.0, result.directional_vote * action_sign))
        return alignment * 12.0

    @staticmethod
    def _liquidity_quality(
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> float:
        result = agent_results.get("universe_liquidity")
        if result is None or result.blockers:
            return 0.0
        score_component = max(0.0, min(1.0, result.score / 100.0)) * 8.0
        latest_price = snapshot.latest_price
        spread = snapshot.spread
        if latest_price is None or spread is None or latest_price <= ZERO:
            return score_component
        spread_ratio = float(spread / latest_price)
        spread_efficiency = max(
            0.0,
            1.0 - min(spread_ratio / float(RiskConfig().maximum_spread_ratio), 1.0),
        )
        return score_component + (spread_efficiency * 4.0)

    def _execution_cost_quality(self, snapshot: MarketSnapshot) -> float:
        latest_price = snapshot.latest_price
        spread = snapshot.spread
        spread_ratio = (
            Decimal("0")
            if latest_price is None or spread is None or latest_price <= ZERO
            else spread / latest_price
        )
        slippage_ratio = self._decimal(
            snapshot.market_metadata.get("estimated_slippage_ratio")
        )
        bounded_spread = min(
            ONE,
            spread_ratio / self.risk_config.maximum_spread_ratio,
        )
        bounded_slippage = min(
            ONE,
            (slippage_ratio or ZERO) / self.risk_config.maximum_slippage_ratio,
        )
        efficiency = ONE - min(ONE, (bounded_spread + bounded_slippage) / Decimal("2"))
        return float(efficiency * Decimal("10"))

    @staticmethod
    def _risk_reward_quality(candidate: TradeCandidate) -> float:
        bounded = min(float(candidate.risk_reward / Decimal("4")), 1.0)
        return max(0.0, bounded) * 8.0

    def _historical_edge_bonus(
        self,
        agent_results: Mapping[str, AgentResult],
        candidate: TradeCandidate,
    ) -> float:
        regime_result = agent_results.get("market_regime")
        regime = self._string_metadata(regime_result, "regime")
        evidence_map = self._mapping_metadata(regime_result, "strategy_regime_research")
        if regime is None or evidence_map is None:
            return 0.0
        strategy_entry = evidence_map.get(candidate.setup_name)
        if not isinstance(strategy_entry, Mapping):
            return 0.0
        regime_entry = strategy_entry.get(regime)
        if not isinstance(regime_entry, Mapping):
            return 0.0
        approved = regime_entry.get("approved") is True
        edge_score = self._float(regime_entry.get("edge_score"))
        if not approved or edge_score is None or edge_score <= 0.0:
            return 0.0
        return min(edge_score, 1.0) * 10.0

    @staticmethod
    def _portfolio_penalty(
        snapshot: MarketSnapshot,
        candidate: TradeCandidate,
    ) -> float:
        concentration_penalty = 0.0
        equity = VirtualMarketCandidateRanker._decimal(
            snapshot.wallet_summary.get("equity_usdt")
        )
        exposure = VirtualMarketCandidateRanker._decimal(
            snapshot.inventory_summary.get("exposure_usdt")
        )
        if (
            candidate.action is Action.BUY
            and equity is not None
            and exposure is not None
            and equity > ZERO
        ):
            concentration_penalty += float(min(exposure / equity, ONE)) * 6.0
        correlation_ratio = VirtualMarketCandidateRanker._decimal(
            snapshot.market_metadata.get("correlation_penalty_ratio")
        )
        if correlation_ratio is not None:
            concentration_penalty += float(min(correlation_ratio, ONE)) * 4.0
        return concentration_penalty

    @staticmethod
    def _mapping_metadata(
        result: AgentResult | None,
        key: str,
    ) -> Mapping[str, object] | None:
        if result is None:
            return None
        value = result.calculation_metadata.get(key)
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _string_metadata(result: AgentResult | None, key: str) -> str | None:
        if result is None:
            return None
        value = result.calculation_metadata.get(key)
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        if not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            decimal_value = Decimal(str(value))
        except InvalidOperation:
            return None
        return (
            decimal_value
            if decimal_value.is_finite() and decimal_value >= ZERO
            else None
        )

    @staticmethod
    def _float(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float, Decimal)):
            return None
        converted = float(value)
        return converted if isfinite(converted) else None

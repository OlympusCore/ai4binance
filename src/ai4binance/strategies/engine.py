"""Deterministic research candidate generation from validated agent evidence."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
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
    is_futures_market_type,
    is_usable_agent_result,
)
from ai4binance.strategies.compression import CompressionBreakoutPlaybookEngine
from ai4binance.strategies.price_action import PriceActionPlaybookEngine
from ai4binance.strategies.ranking import VirtualMarketCandidateRanker
from ai4binance.strategies.regime_playbooks import RegimePlaybookEngine
from ai4binance.strategies.regime_router import DeterministicRegimeRouter
from ai4binance.strategies.registry import (
    GovernedStrategyRegistry,
    PlaybookRegistry,
    VirtualStrategyPortfolioRegistry,
    build_governed_strategy_registry,
    build_playbook_registry,
    build_virtual_strategy_portfolio_registry,
)
from ai4binance.validation.artifacts import ValidationArtifactRegistry


@dataclass(frozen=True, slots=True)
class StrategyEngine:
    """Generate bounded virtual-portfolio research candidates.

    Never grant execution permission.
    """

    registry: PlaybookRegistry = field(default_factory=build_playbook_registry)
    virtual_portfolio: VirtualStrategyPortfolioRegistry = field(
        default_factory=build_virtual_strategy_portfolio_registry
    )
    atr_multiplier: Decimal = Decimal("1.5")
    target_multiplier: Decimal = Decimal("3.0")
    approval_registry: ValidationArtifactRegistry = field(
        default_factory=ValidationArtifactRegistry
    )
    governed_registry: GovernedStrategyRegistry = field(
        default_factory=build_governed_strategy_registry
    )
    candidate_ranker: VirtualMarketCandidateRanker = field(
        default_factory=VirtualMarketCandidateRanker
    )
    regime_router: DeterministicRegimeRouter = field(
        default_factory=DeterministicRegimeRouter
    )
    strategy_version: str = "1"
    config_hash: str = "default"
    candidate_timeframes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.atr_multiplier <= Decimal("0"):
            raise ValueError("atr_multiplier must be positive")
        if self.target_multiplier <= self.atr_multiplier:
            raise ValueError("target_multiplier must exceed atr_multiplier")

    def generate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[TradeCandidate, ...]:
        """Generate bounded virtual-market research candidates.

        The output is limited to canonical families.
        """
        price_action_candidates = PriceActionPlaybookEngine(
            atr_multiplier=self.atr_multiplier,
            target_multiplier=self.target_multiplier,
        ).generate(snapshot, agent_results)
        timeframes = self.candidate_timeframes or (
            "1h" if "1h" in snapshot.timeframes else snapshot.timeframes[0],
        )
        if len(set(timeframes)) != len(timeframes) or any(
            timeframe not in snapshot.timeframes for timeframe in timeframes
        ):
            raise ValueError("candidate timeframes must be unique snapshot timeframes")
        compression_candidates = tuple(
            candidate
            for timeframe in timeframes
            for candidate in CompressionBreakoutPlaybookEngine().generate(
                snapshot, agent_results, timeframe=timeframe
            )
        )
        regime_candidates = tuple(
            candidate
            for timeframe in timeframes
            for candidate in RegimePlaybookEngine().generate(
                snapshot, agent_results, timeframe=timeframe
            )
        )
        supplemental_candidates = (
            *price_action_candidates,
            *compression_candidates,
            *regime_candidates,
        )
        playbook = self.registry.get("trend_continuation")
        if not playbook.implemented or snapshot.latest_price is None:
            return self._approved(supplemental_candidates, snapshot, agent_results)
        trend = agent_results.get("trend")
        structure = agent_results.get("market_structure")
        mtf = agent_results.get("multi_timeframe")
        confluence = agent_results.get("confluence")
        if trend is None or structure is None or mtf is None or confluence is None:
            return self._approved(supplemental_candidates, snapshot, agent_results)
        required = (trend, structure, mtf, confluence)
        if any(not is_usable_agent_result(result) for result in required):
            return self._approved(supplemental_candidates, snapshot, agent_results)
        direction_vote = (trend.directional_vote + structure.directional_vote) / 2
        if abs(direction_vote) < 0.2 or abs(mtf.directional_vote) < 0.1:
            return self._approved(supplemental_candidates, snapshot, agent_results)
        action = Action.BUY if direction_vote > 0 else Action.SELL
        timeframe = "1h" if "1h" in snapshot.timeframes else snapshot.timeframes[0]
        candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
        if len(candles) < 15:
            return self._approved(supplemental_candidates, snapshot, agent_results)
        current_atr = atr(candles, 14)
        entry = snapshot.latest_price
        if current_atr <= Decimal("0") or entry <= current_atr * self.atr_multiplier:
            return self._approved(supplemental_candidates, snapshot, agent_results)
        zone_width = current_atr * Decimal("0.10")
        entry_zone = PriceZone(entry - zone_width, entry + zone_width)
        price_action = agent_results.get("price_action")
        trigger_aligned = (
            price_action is not None
            and is_usable_agent_result(price_action)
            and price_action.directional_vote * direction_vote > 0
        )
        blockers: list[str] = []
        status = CandidateStatus.READY_FOR_RISK
        if not trigger_aligned:
            blockers.append("ENTRY_TRIGGER_MISSING")
            status = CandidateStatus.WAIT_FOR_RETEST
        inventory_action = "NONE"
        if action is Action.SELL:
            if not is_futures_market_type(snapshot.market_type):
                inventory_action = "REDUCE_EXISTING_SPOT_INVENTORY"
                if not snapshot.inventory_summary:
                    blockers.append("INVENTORY_UNKNOWN_FOR_SPOT_SELL")
                    status = CandidateStatus.RESEARCH_ONLY

        if action is Action.BUY:
            stop = entry - (current_atr * self.atr_multiplier)
            target = entry + (current_atr * self.target_multiplier)
        else:
            stop = entry + (current_atr * self.atr_multiplier)
            target = entry - (current_atr * self.target_multiplier)
            if target <= Decimal("0"):
                return self._approved(supplemental_candidates, snapshot, agent_results)
        risk_reward = abs(target - entry) / abs(entry - stop)
        candidate_id = self._candidate_id(snapshot.snapshot_id, action, timeframe)
        trend_candidate = TradeCandidate(
            candidate_id=candidate_id,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            action=action,
            setup_name=playbook.name,
            status=status,
            entry_zone=entry_zone,
            invalidation_level=stop,
            stop_loss=stop,
            take_profit_levels=(target,),
            trailing_stop=stop,
            atr=current_atr,
            risk_reward=risk_reward,
            score=confluence.score,
            confidence=confluence.confidence,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
            inventory_action=inventory_action,
            market_type=snapshot.market_type,
            evidence=(
                "TREND_ALIGNED",
                "STRUCTURE_ALIGNED",
                "MTF_EVALUATED",
                *(
                    price_action.evidence
                    if trigger_aligned and price_action is not None
                    else ()
                ),
            ),
            blockers=tuple(dict.fromkeys(blockers)),
        )
        candidates = (
            trend_candidate,
            *supplemental_candidates,
        )
        return self._approved(candidates, snapshot, agent_results)

    def _approved(
        self,
        candidates: tuple[TradeCandidate, ...],
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[TradeCandidate, ...]:
        portfolio_candidates = self._portfolio_candidates(candidates)
        routed_candidates = self._route_candidates(
            snapshot,
            agent_results,
            portfolio_candidates,
        )
        whale_adjusted = tuple(
            self._apply_whale_fusion(candidate, agent_results)
            for candidate in routed_candidates
        )
        approved = tuple(
            self._apply_approval(candidate) for candidate in whale_adjusted
        )
        return self.candidate_ranker.rank(snapshot, agent_results, approved)

    def _portfolio_candidates(
        self,
        candidates: tuple[TradeCandidate, ...],
    ) -> tuple[TradeCandidate, ...]:
        filtered: list[TradeCandidate] = []
        for candidate in candidates:
            if not self.virtual_portfolio.supports_playbook(candidate.setup_name):
                continue
            strategy = self.virtual_portfolio.resolve_playbook(candidate.setup_name)
            filtered.append(
                replace(
                    candidate,
                    evidence=tuple(
                        dict.fromkeys(
                            (
                                *candidate.evidence,
                                f"VIRTUAL_STRATEGY_ID:{strategy.strategy_id}",
                                f"VIRTUAL_STRATEGY_VERSION:{strategy.strategy_version}",
                            )
                        )
                    ),
                )
            )
        return tuple(filtered)

    def _route_candidates(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        candidates: tuple[TradeCandidate, ...],
    ) -> tuple[TradeCandidate, ...]:
        decision = self.regime_router.decide(agent_results)
        routed: list[TradeCandidate] = []
        for candidate in candidates:
            strategy = self.virtual_portfolio.resolve_playbook(candidate.setup_name)
            routed.append(
                self.regime_router.route_candidate(
                    snapshot,
                    candidate,
                    strategy_id=strategy.strategy_id,
                    decision=decision,
                )
            )
        return tuple(routed)

    @staticmethod
    def _apply_whale_fusion(
        candidate: TradeCandidate,
        agent_results: Mapping[str, AgentResult],
    ) -> TradeCandidate:
        """Apply a bounded supplementary modifier; never create or block a setup."""
        whale = agent_results.get("whale")
        if (
            whale is None
            or not is_usable_agent_result(whale)
            or whale.hard_gate_eligible
            or whale.blockers
        ):
            return candidate
        action_sign = 1.0 if candidate.action is Action.BUY else -1.0
        alignment = whale.directional_vote * action_sign
        modifier = max(-5.0, min(5.0, alignment * whale.confidence * 5.0))
        label = (
            "WHALE_FUSION_ALIGNED_SUPPLEMENTARY"
            if alignment > 0
            else "WHALE_FUSION_CONFLICT_SUPPLEMENTARY"
            if alignment < 0
            else "WHALE_FUSION_NEUTRAL_SUPPLEMENTARY"
        )
        return replace(
            candidate,
            score=max(0.0, min(100.0, candidate.score + modifier)),
            evidence=tuple(dict.fromkeys((*candidate.evidence, label))),
        )

    def _apply_approval(self, candidate: TradeCandidate) -> TradeCandidate:
        status = self.approval_registry.resolve(
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            playbook=candidate.setup_name,
            strategy_version=self.strategy_version,
            config_hash=self.config_hash,
        )
        registry_status = self.registry.get(candidate.setup_name).promotion_status
        governed_status = self.governed_registry.resolve_playbook(
            candidate.setup_name
        ).promotion_status
        effective = (
            ValidationStatus.PAPER_APPROVED
            if status is ValidationStatus.PAPER_APPROVED
            and registry_status is ValidationStatus.PAPER_APPROVED
            and governed_status is ValidationStatus.PAPER_APPROVED
            else ValidationStatus.RESEARCH_ONLY
        )
        return replace(candidate, promotion_status=effective)

    @staticmethod
    def _candidate_id(snapshot_id: str, action: Action, timeframe: str) -> str:
        payload = f"{snapshot_id}|trend_continuation|{action.value}|{timeframe}"
        digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"candidate:{digest}"

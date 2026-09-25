"""Adapters that turn opportunity/recovery artifacts into DGE evaluations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, cast

from ai4binance.core.contracts.virtual_governance import VirtualGovernanceResult
from ai4binance.governance.dge_engine import DecisionGovernanceEngine
from ai4binance.governance.dge_models import (
    DgeGovernanceContext,
    DgeMarketAction,
    DgeMarketPlan,
    DgeSetupTier,
    DgeTradeCandidate,
    GovernedDecision,
)
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    RecoveryCandidate,
    RecoveryLadderStage,
)
from ai4binance.schemas import AgentResult, MarketSnapshot
from ai4binance.strategies.regime_router import DeterministicRegimeRouter

ZERO = Decimal("0")


class _DecisionActionLike(Protocol):
    value: str


class _VirtualCandidateLike(Protocol):
    candidate_id: str
    snapshot_id: str
    symbol: str
    timeframe: str
    action: _DecisionActionLike
    setup_name: str
    score: float
    confidence: float
    entry_price: object
    invalidation_level: object
    stop_loss: object
    take_profit_levels: tuple[object, ...]
    trailing_stop: object
    risk_reward: object
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]


class _VirtualDgeEngineLike(Protocol):
    def evaluate(
        self,
        candidate: DgeTradeCandidate,
        context: DgeGovernanceContext,
    ) -> GovernedDecision: ...


@dataclass(frozen=True, slots=True)
class DgeEvaluationRecord:
    """Replay-ready DGE evaluation bundle."""

    source: str
    candidate: DgeTradeCandidate
    context: DgeGovernanceContext
    decision: GovernedDecision
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("DGE evaluation record source is required")
        if self.decision.candidate_id != self.candidate.candidate_id:
            raise ValueError("DGE record candidate and decision mismatch")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.decision.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE evaluation record cannot authorize execution")


@dataclass(frozen=True, slots=True)
class VirtualMarketDgeAdapter:
    """Evaluate a virtual-market candidate through the canonical DGE."""

    dge: _VirtualDgeEngineLike = field(default_factory=DecisionGovernanceEngine)
    context_builder: (
        Callable[[object, object, object, object], DgeGovernanceContext] | None
    ) = None

    def evaluate(
        self,
        *,
        snapshot: object,
        analysis: object,
        candidate: object,
        portfolio: object,
        market: str,
        quantity: Decimal,
        risk_approved: bool,
        portfolio_verified: bool,
    ) -> VirtualGovernanceResult:
        """Return the dependency-neutral result for one canonical DGE evaluation."""

        try:
            dge_candidate = _virtual_dge_candidate(
                candidate,
                quantity=quantity,
                market=market,
            )
        except (
            ArithmeticError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError("DGE_CANDIDATE_ADAPTATION_FAILED") from error
        try:
            context = (
                self.context_builder(snapshot, analysis, candidate, portfolio)
                if self.context_builder is not None
                else _default_virtual_dge_context(
                    snapshot,
                    analysis,
                    candidate,
                    portfolio,
                    risk_approved=risk_approved,
                    portfolio_verified=portfolio_verified,
                    quantity=quantity,
                )
            )
        except (
            ArithmeticError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError("DGE_CONTEXT_BUILD_FAILED") from error
        if not isinstance(context, DgeGovernanceContext):
            raise ValueError("DGE_CONTEXT_TYPE_INVALID")
        if context.execution_surface is not ExecutionSurface.VIRTUAL_MARKET:
            raise ValueError("DGE_CONTEXT_SURFACE_INVALID")
        try:
            decision = self.dge.evaluate(dge_candidate, context)
        except (
            ArithmeticError,
            AttributeError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError("DGE_ENGINE_EVALUATION_FAILED") from error
        blockers = tuple(
            dict.fromkeys((*decision.hard_blockers, *decision.soft_blockers))
        )
        market_allowed = (
            decision.simulated_spot_allowed
            if market == "SPOT"
            else decision.simulated_futures_allowed
        )
        return VirtualGovernanceResult(
            decision_id=decision.decision_id,
            status=decision.governance_status.value,
            blockers=blockers,
            simulation_allowed=(
                decision.simulated_execution_allowed and market_allowed
            ),
        )


def _virtual_dge_candidate(
    candidate: object,
    *,
    market: str,
    quantity: Decimal,
) -> DgeTradeCandidate:
    candidate_value = cast(_VirtualCandidateLike, candidate)
    evidence = candidate_value.evidence
    if not isinstance(evidence, tuple):
        raise TypeError("virtual DGE candidate evidence must be a tuple")
    entry_price = Decimal(str(candidate_value.entry_price))
    stop_loss = Decimal(str(candidate_value.stop_loss))
    take_profit_levels = tuple(
        Decimal(str(value)) for value in candidate_value.take_profit_levels
    )
    return DgeTradeCandidate(
        candidate_id=str(candidate_value.candidate_id),
        symbol=str(candidate_value.symbol),
        market=market,
        requested_action=DgeMarketAction(str(candidate_value.action.value)),
        setup_name=str(candidate_value.setup_name),
        score=Decimal(str(candidate_value.score)),
        confidence=Decimal(str(candidate_value.confidence)),
        risk_reward=Decimal(str(candidate_value.risk_reward)),
        capital_source="VIRTUAL_PORTFOLIO",
        primary_timeframe=str(candidate_value.timeframe),
        mtf_bias="UNKNOWN",
        regime="UNKNOWN",
        market_plan=DgeMarketPlan(
            entry=entry_price,
            stop_loss=stop_loss,
            invalidation_level=Decimal(str(candidate_value.invalidation_level)),
            take_profit_levels=take_profit_levels,
            trailing_stop=Decimal(str(candidate_value.trailing_stop)),
            size_usdt=quantity * entry_price,
        ),
        evidence_refs=evidence,
    )


def _default_virtual_dge_context(
    snapshot: object,
    analysis: object,
    candidate: object,
    portfolio: object,
    *,
    risk_approved: bool,
    portfolio_verified: bool,
    quantity: Decimal,
) -> DgeGovernanceContext:
    candidate_value = cast(_VirtualCandidateLike, candidate)
    snapshot_id = str(getattr(snapshot, "snapshot_id", "")).strip()
    candidate_id = str(candidate_value.candidate_id).strip()
    candidate_snapshot_id = str(candidate_value.snapshot_id).strip()
    analysis_snapshot_id = str(getattr(analysis, "snapshot_id", snapshot_id)).strip()
    timeframe = str(candidate_value.timeframe).strip()
    timeframes = getattr(snapshot, "timeframes", ())
    created_at = getattr(snapshot, "created_at", None)
    timestamp = created_at.isoformat() if created_at is not None else "UNAVAILABLE"
    candidate_blockers = candidate_value.blockers
    analysis_blockers = getattr(analysis, "blockers", ())
    results = getattr(analysis, "agent_results", {})
    regime_compatible = False
    mtf_aligned = False
    if (
        isinstance(snapshot, MarketSnapshot)
        and isinstance(results, Mapping)
        and all(isinstance(value, AgentResult) for value in results.values())
    ):
        typed_results = {
            name: result
            for name, result in cast(Mapping[str, AgentResult], results).items()
            if result.snapshot_id == snapshot.snapshot_id
            and result.symbol == snapshot.symbol
            and result.timestamp == snapshot.created_at
        }
        route = DeterministicRegimeRouter().decide(typed_results)
        strategy_ids = tuple(
            item.removeprefix("VIRTUAL_STRATEGY_ID:")
            for item in candidate_value.evidence
            if item.startswith("VIRTUAL_STRATEGY_ID:")
        )
        regime_compatible = (
            len(strategy_ids) == 1
            and strategy_ids[0] in route.allowed_strategy_ids
            and candidate_value.action in route.allowed_actions
            and route.wait_reason is None
        )
        mtf = typed_results.get("multi_timeframe")
        mtf_aligned = (
            mtf is not None
            and mtf.snapshot_id == snapshot_id
            and mtf.status.value == "SUCCESS"
            and not mtf.blockers
            and mtf.calculation_metadata.get("alignment_status") == "ALIGNED"
        )
    validation_passed = _validation_gate_passed(analysis)
    final_decision = getattr(analysis, "final_decision", None)
    validation_refs = getattr(final_decision, "supporting_evidence", ())
    oos_passed = validation_passed and any(
        isinstance(ref, str) and ref.startswith("OOS_MATURITY:")
        for ref in validation_refs
    )
    return DgeGovernanceContext(
        context_id=f"virtual-dge-context:{snapshot_id}:{candidate_id}",
        data_snapshot_id=snapshot_id or "UNAVAILABLE",
        semantic_graph_id="UNAVAILABLE",
        position_context_ref=str(getattr(portfolio, "portfolio_id", "UNAVAILABLE")),
        wallet_verified=portfolio_verified,
        snapshot_integrity_verified=(
            bool(snapshot_id)
            and snapshot_id == candidate_snapshot_id == analysis_snapshot_id
        ),
        data_quality_passed=_agent_gate_passed(analysis, "data_quality"),
        required_timeframes_present=(
            isinstance(timeframes, tuple) and timeframe in timeframes
        ),
        liquidity_approved=_agent_gate_passed(analysis, "universe_liquidity"),
        regime_compatible=regime_compatible,
        mtf_aligned=mtf_aligned,
        structure_valid=True,
        negative_evidence_clear=(
            isinstance(candidate_blockers, tuple)
            and isinstance(analysis_blockers, tuple)
            and not _has_any(
                (*candidate_blockers, *analysis_blockers),
                (
                    "NEGATIVE",
                    "CRITICAL_CONFLICT",
                    "FAILED_BREAKOUT",
                    "PUMP",
                    "MANIPULATION",
                ),
            )
        ),
        oos_approved=oos_passed,
        risk_approved=risk_approved,
        validation_approved=validation_passed,
        execution_feasible=risk_approved and quantity > ZERO,
        human_approval_recorded=False,
        no_new_capital_required=True,
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        evidence_refs=tuple(
            dict.fromkeys(
                (
                    snapshot_id or "UNAVAILABLE",
                    str(getattr(portfolio, "portfolio_id", "UNAVAILABLE")),
                )
            )
        ),
        config_hash="unconfigured",
        evaluation_timestamp_utc=timestamp,
    )


def _agent_gate_passed(analysis: object, agent_name: str) -> bool:
    agent_results = getattr(analysis, "agent_results", None)
    if not isinstance(agent_results, Mapping):
        return False
    result = agent_results.get(agent_name)
    if result is None:
        return False
    status = getattr(getattr(result, "status", None), "value", "")
    blockers = getattr(result, "blockers", None)
    return status == "SUCCESS" and isinstance(blockers, tuple) and not blockers


def _validation_gate_passed(analysis: object) -> bool:
    decision = getattr(analysis, "final_decision", None)
    validation_status = getattr(
        getattr(decision, "validation_status", None), "value", ""
    )
    blockers = getattr(decision, "blockers", None)
    return (
        validation_status in {"PAPER_APPROVED", "LIVE_ELIGIBLE"}
        and isinstance(blockers, tuple)
        and not blockers
    )


def evaluate_recovery_radar_with_dge(
    radar: OpportunityRecoveryRadar,
    *,
    dge: DecisionGovernanceEngine | None = None,
    wallet_verified: bool = True,
    human_review_recorded: bool = False,
) -> tuple[DgeEvaluationRecord, ...]:
    """Evaluate every recovery ladder item through DGE without live authority."""

    engine = dge or DecisionGovernanceEngine()
    records: list[DgeEvaluationRecord] = []
    for index, recovery_candidate in enumerate(radar.ladder, start=1):
        candidate = recovery_candidate_to_dge_candidate(recovery_candidate)
        context = recovery_candidate_to_dge_context(
            radar,
            recovery_candidate,
            index=index,
            wallet_verified=wallet_verified,
            human_review_recorded=human_review_recorded,
        )
        decision = engine.evaluate(candidate, context)
        records.append(
            DgeEvaluationRecord(
                source="opportunity_recovery_radar",
                candidate=candidate,
                context=context,
                decision=decision,
            )
        )
    return tuple(records)


def recovery_candidate_to_dge_candidate(
    candidate: RecoveryCandidate,
) -> DgeTradeCandidate:
    """Convert one proposal-only recovery item into a DGE candidate."""

    return DgeTradeCandidate(
        candidate_id=f"recovery:{candidate.candidate_id}",
        symbol=candidate.symbol,
        market="SPOT",
        requested_action=_requested_action(candidate),
        setup_name=candidate.setup_name,
        score=candidate.score,
        confidence=candidate.confidence,
        risk_reward=_risk_reward(candidate),
        capital_source="CURRENT_CAPITAL_REVIEW",
        primary_timeframe=candidate.timeframe,
        setup_tier=_setup_tier(candidate),
        mtf_bias="RECOVERY_RADAR",
        regime="RECOVERY_RESEARCH",
        market_plan=_market_plan(candidate),
        evidence_refs=candidate.evidence_refs or ("recovery_radar",),
    )


def recovery_candidate_to_dge_context(
    radar: OpportunityRecoveryRadar,
    candidate: RecoveryCandidate,
    *,
    index: int,
    wallet_verified: bool,
    human_review_recorded: bool,
) -> DgeGovernanceContext:
    """Build DGE context from recovery blockers and ladder maturity."""

    blockers = tuple(
        blocker
        for blocker in (*radar.blockers, *candidate.blockers)
        if blocker != "LIVE_ORDER_BLOCKED"
    )
    blocker_index = tuple(dict.fromkeys(blockers))
    stage_paper_ready = candidate.ladder_stage is RecoveryLadderStage.PAPER_READY
    return DgeGovernanceContext(
        context_id=f"recovery:{radar.symbol}:context:{index}",
        data_snapshot_id=f"recovery-radar:{radar.symbol}:{radar.range_source}",
        semantic_graph_id=f"recovery-semantic:{radar.symbol}:{index}",
        position_context_ref=f"recovery-inventory:{radar.symbol}",
        wallet_verified=wallet_verified,
        snapshot_integrity_verified=not _has_any(blocker_index, ("CORRUPT",)),
        data_quality_passed=not _has_any(blocker_index, ("DATA", "UNAVAILABLE")),
        required_timeframes_present=not _has_any(blocker_index, ("TIMEFRAME",)),
        liquidity_approved=not _has_any(
            blocker_index,
            ("LIQUIDITY", "SPREAD", "SLIPPAGE", "DEPTH"),
        ),
        regime_compatible=not _has_any(blocker_index, ("REGIME",)),
        mtf_aligned=not _has_any(blocker_index, ("MTF", "HTF")),
        structure_valid=not _has_any(
            blocker_index,
            ("STRUCTURAL", "INVALIDATION", "TRIGGER", "LEVEL_REACTION"),
        ),
        negative_evidence_clear=not _has_any(
            blocker_index,
            ("NEGATIVE", "FAILED_BREAKOUT", "PUMP", "MANIPULATION"),
        ),
        oos_approved=stage_paper_ready and not _has_any(blocker_index, ("OOS",)),
        risk_approved=stage_paper_ready and not _has_any(blocker_index, ("RISK",)),
        validation_approved=False,
        execution_feasible=stage_paper_ready,
        human_approval_recorded=human_review_recorded,
        no_new_capital_required=True,
        blockers=blocker_index,
        evidence_refs=tuple(
            dict.fromkeys(("recovery_radar", *candidate.evidence_refs))
        ),
        config_hash="recovery-dge-adapter-v1",
    )


def _requested_action(candidate: RecoveryCandidate) -> DgeMarketAction:
    action = candidate.review_action.upper()
    if "SELL" in action:
        return DgeMarketAction.SELL
    if "BUY" in action or "REBUY" in action:
        return DgeMarketAction.BUY
    return DgeMarketAction.HOLD


def _setup_tier(candidate: RecoveryCandidate) -> DgeSetupTier:
    grade = candidate.opportunity_grade.upper()
    if grade.startswith("A"):
        return DgeSetupTier.A
    if grade.startswith("B"):
        return DgeSetupTier.B_PLUS
    if grade.startswith("C"):
        return DgeSetupTier.B
    return DgeSetupTier.C


def _risk_reward(candidate: RecoveryCandidate) -> Decimal:
    if candidate.estimated_cycle_gain_ratio > ZERO:
        return max(Decimal("1"), candidate.estimated_cycle_gain_ratio * Decimal("10"))
    return Decimal("1")


def _market_plan(candidate: RecoveryCandidate) -> DgeMarketPlan:
    return DgeMarketPlan(
        entry=candidate.estimated_sell_price,
        stop_loss=None,
        invalidation_level=candidate.estimated_rebuy_price,
        take_profit_levels=(
            (candidate.estimated_rebuy_price,)
            if candidate.estimated_rebuy_price is not None
            else ()
        ),
        size_usdt=None,
    )


def _has_any(blockers: tuple[str, ...], markers: tuple[str, ...]) -> bool:
    return any(marker in blocker for blocker in blockers for marker in markers)

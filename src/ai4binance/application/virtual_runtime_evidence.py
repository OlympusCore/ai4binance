"""Evidence adaptation helpers for bounded virtual runtime evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
)


class ImprovementCandidateEvidence(Protocol):
    """Research proposal supplied by the canonical telemetry owner."""

    @property
    def proposed_experiment(self) -> str: ...


@dataclass(frozen=True, slots=True)
class VirtualHaltReviewPorts:
    """Explicit construction ports wired by the virtual runtime composition."""

    market_type: Callable[[str], object]
    candidate_factory: Callable[..., ImprovementCandidateEvidence]
    metric_factory: Callable[..., object]
    review_factory: Callable[..., object]
    partial_evidence_quality: object
    risk_effectiveness_domain: object
    trading_performance_domain: object
    active_halt_status: object


class _VirtualPortfolioGovernorLike(Protocol):
    @property
    def maximum_consecutive_losses(self) -> int: ...


class _VirtualLossStreakPortfolioLike(Protocol):
    @property
    def portfolio_id(self) -> str: ...

    @property
    def consecutive_losses(self) -> int: ...

    @property
    def max_drawdown_ratio(self) -> Decimal: ...


class _VirtualLossStreakRequestLike(Protocol):
    @property
    def market(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def strategy_id(self) -> str: ...

    @property
    def strategy_version(self) -> str: ...

    @property
    def regime(self) -> str: ...

    @property
    def snapshot_id(self) -> str: ...

    @property
    def decision_id(self) -> str: ...

    @property
    def portfolio(self) -> _VirtualLossStreakPortfolioLike: ...

    @property
    def portfolio_governor(self) -> _VirtualPortfolioGovernorLike: ...


def build_virtual_loss_streak_halt_review(
    request: _VirtualLossStreakRequestLike,
    eligibility: VirtualSimulationEligibility,
    *,
    ports: VirtualHaltReviewPorts,
) -> object | None:
    """Create a research-only halt review when virtual loss streaks trip."""

    if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" not in eligibility.blockers:
        return None

    market_type = ports.market_type(request.market)
    threshold = request.portfolio_governor.maximum_consecutive_losses
    observed_losses = request.portfolio.consecutive_losses
    evidence_refs = (
        request.snapshot_id,
        request.decision_id,
        request.portfolio.portfolio_id,
    )
    candidate = ports.candidate_factory(
        candidate_id=(
            "improvement:loss-streak:"
            f"{request.strategy_id.lower()}:{request.strategy_version.lower()}:"
            f"{request.market.lower()}:{request.regime.lower()}"
        ),
        originating_findings=(
            f"loss-streak-halt:{request.snapshot_id}",
            f"loss-streak-threshold:{threshold}",
        ),
        affected_component="VIRTUAL_MARKET_STRATEGY_RUNTIME",
        affected_rule="VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
        affected_markets=(market_type,),
        affected_regimes=(request.regime,),
        baseline_metrics=(
            ports.metric_factory(
                metric_id="baseline.maximum_consecutive_losses",
                domain=ports.risk_effectiveness_domain,
                value=Decimal(threshold),
                unit="trades",
                evidence_refs=evidence_refs,
            ),
        ),
        observed_metrics=(
            ports.metric_factory(
                metric_id="observed.consecutive_losses",
                domain=ports.risk_effectiveness_domain,
                value=Decimal(observed_losses),
                unit="trades",
                evidence_refs=evidence_refs,
            ),
            ports.metric_factory(
                metric_id="observed.max_drawdown_ratio",
                domain=ports.trading_performance_domain,
                value=request.portfolio.max_drawdown_ratio,
                unit="ratio",
                evidence_refs=evidence_refs,
            ),
        ),
        sample_size=max(observed_losses, 1),
        evidence_quality=ports.partial_evidence_quality,
        confidence=Decimal("0.60"),
        hypothesis=(
            f"{request.strategy_id} in {request.regime} exceeded the governed "
            "loss-streak limit; entry gating, regime fit, or exit protection "
            "is likely under-calibrated."
        ),
        proposed_experiment=(
            "Freeze the halted scope, replay the last three losses with bounded "
            "virtual evidence, compare planned versus realized risk, and stage "
            "parameter or gating changes as research-only candidates."
        ),
        risk_delta_usdt=Decimal("0"),
    )
    findings = (
        (
            f"Observed `{observed_losses}` consecutive losses against the governed "
            f"limit `{threshold}`."
        ),
        (
            "The bounded autonomy scope is halted before a new simulated entry "
            "can be opened."
        ),
        (
            "A research-only improvement candidate was staged for replay, tuning, "
            "and root-cause review."
        ),
    )
    root_cause_tags = (
        "ENTRY_GATING_REVIEW",
        "REGIME_FIT_REVIEW",
        "EXIT_PROTECTION_REVIEW",
    )
    root_cause_summary = (
        "Loss streak suggests entry gating, regime fit, or exit protection "
        "is under-calibrated for the halted bounded scope."
    )
    next_bounded_experiment = candidate.proposed_experiment
    reset_criteria = (
        (
            "Resume only when a later request supplies "
            "`portfolio.consecutive_losses < maximum_consecutive_losses`."
        ),
        (
            "Keep the staged improvement candidate `RESEARCH_ONLY` and "
            "`LIVE_ORDER_BLOCKED`."
        ),
        (
            "Re-evaluate DGE, risk, validation, and feasibility blockers on "
            "the next bounded simulation request before allowing entry."
        ),
    )
    return ports.review_factory(
        review_id=(
            f"virtual-loss-streak-halt:{request.strategy_id.lower()}:{request.market.lower()}:{request.snapshot_id}"
        ),
        snapshot_id=request.snapshot_id,
        decision_id=request.decision_id,
        portfolio_id=request.portfolio.portfolio_id,
        halt_scope=f"{request.market}:{request.strategy_id}:{request.regime}",
        status=ports.active_halt_status,
        trigger_blocker="VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
        market=request.market,
        symbol=request.symbol,
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        regime=request.regime,
        consecutive_losses=observed_losses,
        maximum_consecutive_losses=threshold,
        findings=findings,
        root_cause_tags=root_cause_tags,
        root_cause_summary=root_cause_summary,
        next_bounded_experiment=next_bounded_experiment,
        reset_criteria=reset_criteria,
        improvement_candidates=(candidate,),
    )

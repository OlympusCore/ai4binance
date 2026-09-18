"""Evidence adaptation helpers for bounded virtual runtime evaluation."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from importlib import import_module
from typing import Protocol, cast

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
)

_decision_telemetry = import_module("ai4binance.ops.decision_telemetry")
EvidenceQuality = _decision_telemetry.EvidenceQuality
ImprovementCandidate = _decision_telemetry.ImprovementCandidate
MetricEvidence = _decision_telemetry.MetricEvidence
TelemetryDomain = _decision_telemetry.TelemetryDomain


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


class _VirtualMarketRuntimeLike(Protocol):
    @staticmethod
    def _market_type(market: str) -> object: ...


def build_virtual_loss_streak_halt_review(
    request: _VirtualLossStreakRequestLike,
    eligibility: VirtualSimulationEligibility,
) -> object | None:
    """Create a research-only halt review when virtual loss streaks trip."""

    if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" not in eligibility.blockers:
        return None

    research_virtual_runtime = import_module("ai4binance.research.virtual_runtime")
    zero = research_virtual_runtime.ZERO
    virtual_autonomy_halt_status = research_virtual_runtime.VirtualAutonomyHaltStatus
    virtual_market_runtime = cast(
        type[_VirtualMarketRuntimeLike],
        research_virtual_runtime.VirtualMarketRuntime,
    )
    virtual_loss_streak_halt_review = cast(
        Callable[..., object],
        research_virtual_runtime.VirtualLossStreakHaltReview,
    )

    market_type = virtual_market_runtime._market_type(request.market)
    threshold = request.portfolio_governor.maximum_consecutive_losses
    observed_losses = request.portfolio.consecutive_losses
    evidence_refs = (
        request.snapshot_id,
        request.decision_id,
        request.portfolio.portfolio_id,
    )
    candidate = ImprovementCandidate(
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
            MetricEvidence(
                metric_id="baseline.maximum_consecutive_losses",
                domain=TelemetryDomain.RISK_EFFECTIVENESS,
                value=Decimal(threshold),
                unit="trades",
                evidence_refs=evidence_refs,
            ),
        ),
        observed_metrics=(
            MetricEvidence(
                metric_id="observed.consecutive_losses",
                domain=TelemetryDomain.RISK_EFFECTIVENESS,
                value=Decimal(observed_losses),
                unit="trades",
                evidence_refs=evidence_refs,
            ),
            MetricEvidence(
                metric_id="observed.max_drawdown_ratio",
                domain=TelemetryDomain.TRADING_PERFORMANCE,
                value=request.portfolio.max_drawdown_ratio,
                unit="ratio",
                evidence_refs=evidence_refs,
            ),
        ),
        sample_size=max(observed_losses, 1),
        evidence_quality=EvidenceQuality.PARTIAL,
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
        risk_delta_usdt=zero,
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
    return virtual_loss_streak_halt_review(
        review_id=(
            f"virtual-loss-streak-halt:{request.strategy_id.lower()}:{request.market.lower()}:{request.snapshot_id}"
        ),
        snapshot_id=request.snapshot_id,
        decision_id=request.decision_id,
        portfolio_id=request.portfolio.portfolio_id,
        halt_scope=f"{request.market}:{request.strategy_id}:{request.regime}",
        status=virtual_autonomy_halt_status.ACTIVE,
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

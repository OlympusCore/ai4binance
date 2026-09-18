"""Full-system historical replay evidence orchestration.

This module composes the canonical replay, virtual runtime, performance,
acceptance, persistence, reporting, and controlled-learning boundaries.  It
does not authorize exchange execution and it does not implement a strategy
backtester or a second wallet-accounting truth.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from ai4binance.application.learning_loop import (
    ControlledLearningLoop,
    LearningLoopResult,
)
from ai4binance.historical_replay_state import HistoricalReplayStateStore
from ai4binance.ops.decision_telemetry import (
    DgeEffectivenessMetrics,
    DgeRuleEffectivenessMetrics,
)
from ai4binance.ops.user_reports import (
    UserReportPaths,
    render_professional_summary,
)
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    TradeDirection,
)
from ai4binance.research.backtesting.robustness import BacktestRobustnessReport
from ai4binance.research.historical_replay import VirtualWalletEpoch
from ai4binance.research.virtual_market import (
    DailyEquityPoint,
    MarketAcceptanceResult,
    SystemResearchAcceptance,
    VirtualMarket,
)
from ai4binance.research.virtual_runtime import (
    VirtualClosedTradeRecord,
    VirtualEvidenceSurfaceAdapter,
    VirtualMarketRuntime,
    VirtualPortfolioPerformance,
    VirtualPortfolioState,
    VirtualResearchEvidenceSurface,
    VirtualTradeAttributionLedger,
)
from ai4binance.research_runtime import (
    HistoricalMarketEquityCurve,
    HistoricalReplayCycleResult,
    HistoricalReplayRunResult,
)
from ai4binance.validation.models import WalkForwardReport

ZERO = Decimal("0")
ONE = Decimal("1")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DGE_SIMULATION_SENTINEL = "DGE_SIMULATION_NOT_APPROVED"


@dataclass(frozen=True, slots=True)
class HistoricalReplayMetric:
    """One deterministic KPI with explicit insufficient-data semantics."""

    metric_id: str
    value: Decimal | int | None
    unit: str
    supported: bool = True

    def __post_init__(self) -> None:
        if not self.metric_id.strip() or not self.unit.strip():
            raise ValueError("historical replay metric identity is required")
        if self.supported != (self.value is not None):
            raise ValueError(
                "historical replay metric support must match value availability"
            )
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("historical replay metric value must be finite")
        if isinstance(self.value, int) and self.value < 0:
            raise ValueError("historical replay count metric cannot be negative")

    def to_payload(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "value": str(self.value) if isinstance(self.value, Decimal) else self.value,
            "unit": self.unit,
            "status": "AVAILABLE" if self.supported else "INSUFFICIENT_DATA",
        }


@dataclass(frozen=True, slots=True)
class HistoricalDgeCounterfactualOutcome:
    """Exact, research-only outcome from a one-rule DGE shadow replay."""

    decision_id: str
    market: VirtualMarket
    rule_id: str
    outcome_observed_at: datetime
    net_pnl_usdt: Decimal
    execution_model_sha256: str
    replay_state_sha256: str
    evidence_refs: tuple[str, ...]
    higher_authority_vetoes_retained: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        market = (
            self.market
            if isinstance(self.market, VirtualMarket)
            else VirtualMarket(str(self.market).strip().upper())
        )
        object.__setattr__(self, "market", market)
        if not self.decision_id.strip() or not self.rule_id.strip():
            raise ValueError("DGE counterfactual decision and rule ids are required")
        if self.rule_id == _DGE_SIMULATION_SENTINEL:
            raise ValueError("DGE simulation sentinel is not an ablatable rule")
        _require_utc("DGE counterfactual outcome timestamp", self.outcome_observed_at)
        if not self.net_pnl_usdt.is_finite():
            raise ValueError("DGE counterfactual outcome PnL must be finite")
        for label, value in (
            ("execution model", self.execution_model_sha256),
            ("replay state", self.replay_state_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"DGE counterfactual {label} SHA-256 is invalid")
        _require_unique_nonblank("DGE counterfactual evidence refs", self.evidence_refs)
        if (
            not self.higher_authority_vetoes_retained
            or self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "DGE counterfactual must retain higher-authority vetoes and stay "
                "research only"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "counterfactual_type": "RULE_ABLATION",
            "decision_id": self.decision_id,
            "market": self.market.value,
            "rule_id": self.rule_id,
            "outcome_observed_at": self.outcome_observed_at.isoformat(),
            "net_pnl_usdt": str(self.net_pnl_usdt),
            "execution_model_sha256": self.execution_model_sha256,
            "replay_state_sha256": self.replay_state_sha256,
            "evidence_refs": list(self.evidence_refs),
            "higher_authority_vetoes_retained": True,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalMarketPerformanceEvaluation:
    """Canonical market performance plus complete deterministic KPI groups."""

    market: VirtualMarket
    portfolio_performance: VirtualPortfolioPerformance
    attribution_ledger: VirtualTradeAttributionLedger
    common_kpis: tuple[HistoricalReplayMetric, ...]
    market_specific_kpis: tuple[HistoricalReplayMetric, ...]
    operational_kpis: tuple[HistoricalReplayMetric, ...]

    def __post_init__(self) -> None:
        if self.portfolio_performance.market != self.market.value:
            raise ValueError("historical market performance must match market")
        all_metrics = (
            *self.common_kpis,
            *self.market_specific_kpis,
            *self.operational_kpis,
        )
        metric_ids = tuple(metric.metric_id for metric in all_metrics)
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("historical market performance metric ids must be unique")

    def to_payload(self) -> dict[str, object]:
        return {
            "market": self.market.value,
            "portfolio_performance": {
                "starting_equity_usdt": str(
                    self.portfolio_performance.starting_equity_usdt
                ),
                "ending_equity_usdt": str(
                    self.portfolio_performance.ending_equity_usdt
                ),
                "observation_count": self.portfolio_performance.observation_count,
                "sample_period_seconds": (
                    self.portfolio_performance.sample_period_seconds
                ),
                "net_return": str(self.portfolio_performance.net_return),
                "annualized_return": _decimal_text(
                    self.portfolio_performance.annualized_return
                ),
                "max_drawdown": str(self.portfolio_performance.max_drawdown),
                "portfolio_sharpe": _decimal_text(
                    self.portfolio_performance.portfolio_sharpe
                ),
                "portfolio_sortino": _decimal_text(
                    self.portfolio_performance.portfolio_sortino
                ),
            },
            "common_kpis": [metric.to_payload() for metric in self.common_kpis],
            "market_specific_kpis": [
                metric.to_payload() for metric in self.market_specific_kpis
            ],
            "operational_kpis": [
                metric.to_payload() for metric in self.operational_kpis
            ],
        }


@dataclass(frozen=True, slots=True)
class HistoricalMarketReplayEvaluation:
    """One market's replay evidence with independent acceptance authority."""

    market: VirtualMarket
    wallet_epoch: VirtualWalletEpoch
    performance: HistoricalMarketPerformanceEvaluation
    dge_metrics: DgeEffectivenessMetrics
    evidence_surface: VirtualResearchEvidenceSurface
    adapter: VirtualEvidenceSurfaceAdapter
    acceptance: MarketAcceptanceResult
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.wallet_epoch.market is not self.market
            or self.wallet_epoch.portfolio_id
            != self.evidence_surface.market_performance.portfolio_id
            or self.wallet_epoch.initial_capital_usdt
            != self.performance.portfolio_performance.starting_equity_usdt
            or self.performance.market is not self.market
            or self.evidence_surface.market_performance.market is not self.market
            or self.adapter.market != self.market.value
            or self.acceptance.market is not self.market
        ):
            raise ValueError("historical market evaluation identity is inconsistent")
        if self.adapter.market_acceptance_result != self.acceptance:
            raise ValueError(
                "historical market adapter must expose exact acceptance result"
            )
        if self.blockers != self.evidence_surface.blockers:
            raise ValueError("historical market blockers must match evidence surface")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical market evaluation cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "market": self.market.value,
            "wallet_epoch": self.wallet_epoch.to_payload(),
            "performance": self.performance.to_payload(),
            "dge_effectiveness": self.dge_metrics.to_payload(),
            "acceptance": self.acceptance.to_payload(),
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplaySystemEvaluation:
    """Market-scoped replay evaluation with optional conjunctive system result."""

    replay_result: HistoricalReplayRunResult
    markets: tuple[HistoricalMarketReplayEvaluation, ...]
    system_acceptance: SystemResearchAcceptance | None
    learning_result: LearningLoopResult | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        by_market = {item.market: item for item in self.markets}
        requested_markets = {
            selection.market
            for selection in self.replay_result.request.market_selections
        }
        if not by_market or set(by_market) != requested_markets:
            raise ValueError(
                "historical replay evaluation must cover the exact requested markets"
            )
        both_markets = {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
        if requested_markets == both_markets:
            if self.system_acceptance is None or (
                self.system_acceptance.spot != by_market[VirtualMarket.SPOT].acceptance
                or self.system_acceptance.futures
                != by_market[VirtualMarket.USD_M_FUTURES].acceptance
            ):
                raise ValueError(
                    "system acceptance must derive from exact independent "
                    "market results"
                )
        elif self.system_acceptance is not None:
            raise ValueError(
                "single-market replay evaluation cannot fabricate system acceptance"
            )
        request_epochs = {
            epoch.market: epoch for epoch in self.replay_result.request.wallet_epochs
        }
        if any(
            item.wallet_epoch != request_epochs.get(item.market)
            for item in self.markets
        ):
            raise ValueError(
                "historical replay evaluation must preserve exact wallet epochs"
            )
        if self.learning_result is not None and self.learning_result.execution_allowed:
            raise ValueError("historical replay learning cannot authorize execution")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay evaluation cannot authorize trading")

    def market(self, market: VirtualMarket) -> HistoricalMarketReplayEvaluation:
        return next(item for item in self.markets if item.market is market)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": "HistoricalReplaySystemEvaluation/v1",
            "run_id": self.replay_result.request.run_id,
            "evidence_class": "HISTORICAL_REPLAY",
            "replay_state_sha256": self.replay_result.semantic_result_sha256,
            "system_version": self.replay_result.request.system_version.to_payload(),
            "markets": [item.to_payload() for item in self.markets],
            "system_acceptance": (
                self.system_acceptance.to_payload()
                if self.system_acceptance is not None
                else None
            ),
            "learning_summary_id": (
                self.learning_result.summary.summary_id
                if self.learning_result is not None
                else None
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayPublication:
    """Verified local publication and wallet-checkpoint result."""

    state_path: Path
    state_persisted: bool
    market_report_paths: tuple[tuple[VirtualMarket, UserReportPaths], ...]
    system_acceptance_paths: UserReportPaths | None
    system_evaluation_paths: UserReportPaths
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        markets = tuple(market for market, _ in self.market_report_paths)
        if (
            not markets
            or len(set(markets)) != len(markets)
            or not set(markets).issubset(
                {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
            )
        ):
            raise ValueError(
                "historical replay publication requires unique supported markets"
            )
        if (len(markets) == 2) != (self.system_acceptance_paths is not None):
            raise ValueError(
                "system acceptance publication requires both market results"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay publication cannot authorize trading")


@dataclass(frozen=True, slots=True)
class HistoricalReplaySystemEvaluator:
    """Compose canonical market-scoped replay evidence without parallel truths."""

    runtime: VirtualMarketRuntime = field(default_factory=VirtualMarketRuntime)

    def evaluate(
        self,
        result: HistoricalReplayRunResult,
        *,
        walk_forward_reports: Mapping[VirtualMarket | str, WalkForwardReport]
        | None = None,
        robustness_reports: Mapping[VirtualMarket | str, BacktestRobustnessReport]
        | None = None,
        dge_counterfactuals: Sequence[HistoricalDgeCounterfactualOutcome] = (),
        reproducibility_reference_sha256: str | None = None,
        learning_loop: ControlledLearningLoop | None = None,
    ) -> HistoricalReplaySystemEvaluation:
        """Evaluate requested markets and preserve hard evidence boundaries."""

        _require_requested_market_result(result)
        walk_forward = _normalize_market_mapping(walk_forward_reports or {})
        robustness = _normalize_market_mapping(robustness_reports or {})
        outcomes = tuple(dge_counterfactuals)
        _require_unique_counterfactuals(outcomes)
        replay_hash = result.semantic_result_sha256
        if reproducibility_reference_sha256 is not None and not _SHA256_RE.fullmatch(
            reproducibility_reference_sha256
        ):
            raise ValueError("reproducibility reference SHA-256 is invalid")
        reproducibility_rate = (
            ONE if reproducibility_reference_sha256 == replay_hash else ZERO
        )
        evaluations: list[HistoricalMarketReplayEvaluation] = []
        requested_markets = tuple(
            sorted(
                (selection.market for selection in result.request.market_selections),
                key=lambda market: market.value,
            )
        )
        for market in requested_markets:
            market_cycles = tuple(
                cycle
                for cycle in result.cycles
                if cycle.replay_snapshot.market == market.value
            )
            market_trades = tuple(
                trade
                for trade in result.closed_trades
                if trade.attribution.market.strip().upper() == market.value
            )
            curve = next(
                curve for curve in result.equity_curves if curve.market is market
            )
            portfolio_performance = self.runtime.calculate_portfolio_performance(
                market=market.value,
                equity_curve=curve.points,
            )
            attribution = self.runtime.build_trade_attribution_ledger(market_trades)
            dge_metrics, dge_blockers = _dge_effectiveness(
                result=result,
                market=market,
                cycles=market_cycles,
                trades=market_trades,
                curve=curve,
                outcomes=outcomes,
                reproducibility_rate=reproducibility_rate,
                runtime=self.runtime,
            )
            evidence_blockers = _market_evidence_blockers(
                result=result,
                market=market,
                cycles=market_cycles,
                walk_forward_report=walk_forward.get(market),
                robustness_report=robustness.get(market),
                reproducibility_reference_sha256=reproducibility_reference_sha256,
                dge_blockers=dge_blockers,
            )
            latest = max(cycle.replay_snapshot.created_at for cycle in market_cycles)
            feature_warmup = min(
                binding.coverage_start
                for binding in result.request.dataset_bindings
                if binding.market is market
            )
            epoch = next(
                epoch
                for epoch in result.request.wallet_epochs
                if epoch.market is market
            )
            peak_margin = _peak_margin_utilization(market, market_cycles)
            surface = self.runtime.build_research_evidence_surface(
                session_id=f"historical-replay:{result.request.run_id}:{market.value}",
                portfolio_id=epoch.portfolio_id,
                generation=1,
                configured_start_at=result.request.start_at,
                feature_warmup_start=feature_warmup,
                last_replayed_at=latest,
                market=market.value,
                timeframe="+".join(result.request.timeframes),
                portfolio_performance=portfolio_performance,
                attribution_ledger=attribution,
                walk_forward_report=walk_forward.get(market),
                robustness_report=robustness.get(market),
                dge_metrics=dge_metrics,
                replay_state_hash=replay_hash,
                observed_at=latest,
                peak_margin_utilization=peak_margin,
                critical_data_gaps=sum(
                    cycle.replay_snapshot.execution_context is None
                    for cycle in market_cycles
                ),
                critical_data_quality_failure=any(
                    str(cycle.replay_snapshot.snapshot.data_quality.value)
                    != "DATA_VALID"
                    for cycle in market_cycles
                ),
                applied_duplicate_economic_events=0,
                lookahead_violations=0,
                liquidation_events=sum(
                    trade.exit_reason is BacktestExitReason.LIQUIDATION
                    for trade in market_trades
                ),
                decision_reproducibility_rate=reproducibility_rate,
                evidence_blockers=evidence_blockers,
            )
            adapter = self.runtime.adapt_evidence_surface(surface)
            acceptance = adapter.market_acceptance_result
            if acceptance is None:
                raise ValueError(
                    "historical replay research adapter requires market acceptance"
                )
            evaluations.append(
                HistoricalMarketReplayEvaluation(
                    market=market,
                    wallet_epoch=epoch,
                    performance=_performance_evaluation(
                        market=market,
                        cycles=market_cycles,
                        trades=market_trades,
                        curve=curve,
                        portfolio_performance=portfolio_performance,
                        attribution=attribution,
                        reproducibility_rate=reproducibility_rate,
                        peak_margin_utilization=peak_margin,
                    ),
                    dge_metrics=dge_metrics,
                    evidence_surface=surface,
                    adapter=adapter,
                    acceptance=acceptance,
                    blockers=surface.blockers,
                )
            )
        ordered = tuple(sorted(evaluations, key=lambda item: item.market.value))
        by_market = {item.market: item for item in ordered}
        system_acceptance = (
            SystemResearchAcceptance.derive(
                by_market[VirtualMarket.SPOT].acceptance,
                by_market[VirtualMarket.USD_M_FUTURES].acceptance,
            )
            if set(requested_markets)
            == {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
            else None
        )
        learning_result = (
            learning_loop.run(
                created_at=max(
                    cycle.replay_snapshot.created_at for cycle in result.cycles
                ),
                performance_snapshots=tuple(
                    item.evidence_surface.performance_snapshot for item in ordered
                ),
            )
            if learning_loop is not None
            else None
        )
        return HistoricalReplaySystemEvaluation(
            replay_result=result,
            markets=ordered,
            system_acceptance=system_acceptance,
            learning_result=learning_result,
        )

    def persist_and_publish(
        self,
        evaluation: HistoricalReplaySystemEvaluation,
        *,
        root: Path,
        stamp: str,
        state_store: HistoricalReplayStateStore | None = None,
    ) -> HistoricalReplayPublication:
        """Persist the wallet projection and publish existing YKB input surfaces."""

        from ai4binance.historical_replay_persistence import (
            HistoricalReplayEvidencePublisher,
        )

        publication = HistoricalReplayEvidencePublisher(self.runtime).publish(
            evaluation,
            root=root,
            stamp=stamp,
            state_store=state_store,
            render_evaluation=_render_system_evaluation_markdown,
            publication_factory=HistoricalReplayPublication,
        )
        if not isinstance(publication, HistoricalReplayPublication):
            raise TypeError("historical replay publisher returned invalid contract")
        return publication


def _render_system_evaluation_markdown(
    evaluation: HistoricalReplaySystemEvaluation,
) -> str:
    observed_at = max(
        cycle.replay_snapshot.created_at for cycle in evaluation.replay_result.cycles
    )
    sections_list: list[tuple[str, tuple[str, ...]]] = []
    for item in evaluation.markets:
        performance = item.performance.portfolio_performance
        sections_list.append(
            (
                item.market.value,
                (
                    f"- Wallet epoch: `{item.wallet_epoch.epoch_id}`",
                    (
                        "- System version segment: "
                        f"`{item.wallet_epoch.system_segment_sha256}`"
                    ),
                    (
                        "- Initial/ending equity: "
                        f"`{performance.starting_equity_usdt}` / "
                        f"`{performance.ending_equity_usdt}` USDT"
                    ),
                    f"- Acceptance: `{item.acceptance.status.value}`",
                    f"- DGE effectiveness: `{item.dge_metrics.status.value}`",
                ),
            )
        )
    sections = tuple(sections_list)
    blockers = tuple(
        dict.fromkeys(
            blocker for item in evaluation.markets for blocker in item.blockers
        )
    )
    return render_professional_summary(
        title="Historical Replay System Evaluation",
        observed_at=observed_at.isoformat(),
        status=(
            evaluation.system_acceptance.status.value
            if evaluation.system_acceptance is not None
            else evaluation.markets[0].acceptance.status.value
        ),
        summary=(
            "This report preserves requested-market performance, acceptance, DGE "
            "effectiveness, wallet epoch, and system-version evidence without "
            "fabricating missing market results."
        ),
        sections=sections,
        blockers=blockers,
    )


def _require_requested_market_result(result: HistoricalReplayRunResult) -> None:
    markets = {selection.market for selection in result.request.market_selections}
    if not markets or not markets.issubset(
        {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
    ):
        raise ValueError("historical replay evaluation requires supported markets")
    cycle_markets = {cycle.replay_snapshot.market for cycle in result.cycles}
    if cycle_markets != {market.value for market in markets}:
        raise ValueError(
            "historical replay result requires cycles for every requested market"
        )


def _normalize_market_mapping[T](
    values: Mapping[VirtualMarket | str, T],
) -> dict[VirtualMarket, T]:
    normalized: dict[VirtualMarket, T] = {}
    for key, value in values.items():
        market = (
            key
            if isinstance(key, VirtualMarket)
            else VirtualMarket(str(key).strip().upper())
        )
        if market in normalized:
            raise ValueError("market evidence mapping contains duplicate markets")
        normalized[market] = value
    return normalized


def _require_unique_counterfactuals(
    outcomes: tuple[HistoricalDgeCounterfactualOutcome, ...],
) -> None:
    keys = tuple((item.decision_id, item.rule_id) for item in outcomes)
    if len(set(keys)) != len(keys):
        raise ValueError("DGE counterfactual outcomes must be unique per rule")


def _eligible_dge_rules(cycle: HistoricalReplayCycleResult) -> tuple[str, ...]:
    request = cycle.workflow.virtual_runtime_request
    if request is None:
        return ()
    return tuple(
        blocker
        for blocker in request.dge_blockers
        if blocker != _DGE_SIMULATION_SENTINEL and blocker.startswith("DGE_")
    )


def _dge_effectiveness(
    *,
    result: HistoricalReplayRunResult,
    market: VirtualMarket,
    cycles: tuple[HistoricalReplayCycleResult, ...],
    trades: tuple[VirtualClosedTradeRecord, ...],
    curve: HistoricalMarketEquityCurve,
    outcomes: tuple[HistoricalDgeCounterfactualOutcome, ...],
    reproducibility_rate: Decimal,
    runtime: VirtualMarketRuntime,
) -> tuple[DgeEffectivenessMetrics, tuple[str, ...]]:
    decision_cycles = tuple(
        cycle for cycle in cycles if cycle.workflow.virtual_runtime_request is not None
    )
    cycle_by_decision = {
        cycle.workflow.virtual_runtime_request.decision_id: cycle
        for cycle in decision_cycles
        if cycle.workflow.virtual_runtime_request is not None
    }
    activations = tuple(
        (cycle, rule)
        for cycle in decision_cycles
        for rule in _eligible_dge_rules(cycle)
    )
    activation_keys = {
        (cycle.workflow.virtual_runtime_request.decision_id, rule)
        for cycle, rule in activations
        if cycle.workflow.virtual_runtime_request is not None
    }
    market_outcomes = tuple(item for item in outcomes if item.market is market)
    provided_keys = {(item.decision_id, item.rule_id) for item in market_outcomes}
    unknown = provided_keys - activation_keys
    if unknown:
        raise ValueError("DGE counterfactual references unknown rule activation")
    for outcome in market_outcomes:
        cycle = cycle_by_decision[outcome.decision_id]
        request = cycle.workflow.virtual_runtime_request
        if request is None:
            raise ValueError("DGE counterfactual decision request is unavailable")
        if (
            request.analysis_blockers
            or request.candidate_blockers
            or request.risk_blockers
            or request.validation_blockers
        ):
            raise ValueError("DGE_SHADOW_CANNOT_BYPASS_HIGHER_AUTHORITY_VETO")
        if (
            outcome.execution_model_sha256
            != result.request.system_version.execution_model_sha256
        ):
            raise ValueError("DGE counterfactual execution model mismatch")
        if outcome.replay_state_sha256 != result.semantic_result_sha256:
            raise ValueError("DGE counterfactual replay state mismatch")
        if not (
            cycle.replay_snapshot.created_at
            <= outcome.outcome_observed_at
            <= max(item.replay_snapshot.created_at for item in cycles)
        ):
            raise ValueError("DGE counterfactual outcome is outside replay time")
    outcome_by_key = {
        (item.decision_id, item.rule_id): item for item in market_outcomes
    }
    evaluated = tuple(
        outcome_by_key[key] for key in sorted(activation_keys) if key in outcome_by_key
    )
    protective = tuple(item for item in evaluated if item.net_pnl_usdt < ZERO)
    false_blocks = tuple(item for item in evaluated if item.net_pnl_usdt > ZERO)
    loss_avoided = sum((abs(item.net_pnl_usdt) for item in protective), ZERO)
    profit_missed = sum((item.net_pnl_usdt for item in false_blocks), ZERO)
    rules: list[DgeRuleEffectivenessMetrics] = []
    for rule_id in sorted({rule for _, rule in activations}):
        rule_activations = tuple(item for item in activations if item[1] == rule_id)
        rule_outcomes = tuple(item for item in evaluated if item.rule_id == rule_id)
        rule_protective = tuple(
            item for item in rule_outcomes if item.net_pnl_usdt < ZERO
        )
        rule_false = tuple(item for item in rule_outcomes if item.net_pnl_usdt > ZERO)
        rules.append(
            DgeRuleEffectivenessMetrics(
                rule_id=rule_id,
                activation_count=len(rule_activations),
                evaluated_count=len(rule_outcomes),
                protective_block_count=len(rule_protective),
                false_block_count=len(rule_false),
                loss_avoided_usdt=sum(
                    (abs(item.net_pnl_usdt) for item in rule_protective), ZERO
                ),
                profit_missed_usdt=sum(
                    (item.net_pnl_usdt for item in rule_false), ZERO
                ),
                evidence_refs=tuple(
                    dict.fromkeys(
                        ref for item in rule_outcomes for ref in item.evidence_refs
                    )
                )
                or (f"dge-rule:{rule_id}:evidence-missing",),
            )
        )
    approved_decisions = sum(
        not request.dge_blockers and request.dge_simulation_allowed
        for request in (
            cycle.workflow.virtual_runtime_request for cycle in decision_cycles
        )
        if request is not None
    )
    sample_size = max(1, approved_decisions + len(activations))
    counterfactual_curve = _counterfactual_equity_curve(curve, evaluated)
    drawdown_without = runtime.calculate_portfolio_performance(
        market=market.value,
        equity_curve=counterfactual_curve,
    ).max_drawdown
    blockers: list[str] = []
    if not activations:
        blockers.append("DGE_COUNTERFACTUAL_NOT_EVALUABLE")
    elif len(evaluated) < len(activations):
        blockers.append("DGE_COUNTERFACTUAL_OUTCOME_EVIDENCE_INCOMPLETE")
    non_evaluable_dge = tuple(
        blocker
        for cycle in decision_cycles
        for blocker in (
            cycle.workflow.virtual_runtime_request.dge_blockers
            if cycle.workflow.virtual_runtime_request is not None
            else ()
        )
        if blocker != _DGE_SIMULATION_SENTINEL and not blocker.startswith("DGE_")
    )
    if non_evaluable_dge:
        blockers.append("DGE_HIGHER_AUTHORITY_BLOCKER_NOT_ABLATABLE")
    approved_loss_count = sum(trade.net_pnl_usdt < ZERO for trade in trades)
    return (
        DgeEffectivenessMetrics(
            sample_size=sample_size,
            intervention_count=len(activations),
            protective_block_count=len(protective),
            false_block_count=len(false_blocks),
            loss_avoided_usdt=loss_avoided,
            profit_missed_usdt=profit_missed,
            drawdown_without_dge_pct=drawdown_without,
            drawdown_with_dge_pct=runtime.calculate_portfolio_performance(
                market=market.value,
                equity_curve=curve.points,
            ).max_drawdown,
            counterfactual_expectancy_delta_usdt=(
                (loss_avoided - profit_missed) / Decimal(len(evaluated))
                if evaluated
                else ZERO
            ),
            computed_at=max(cycle.replay_snapshot.created_at for cycle in cycles),
            approved_trade_count=len(trades),
            approved_trade_loss_count=approved_loss_count,
            approved_trade_net_pnl_usdt=sum(
                (trade.net_pnl_usdt for trade in trades), ZERO
            ),
            approved_decision_count=approved_decisions,
            counterfactual_evaluated_count=len(evaluated),
            decision_stability_rate=reproducibility_rate,
            replay_match_rate=reproducibility_rate,
            rule_metrics=tuple(rules),
        ),
        tuple(dict.fromkeys(blockers)),
    )


def _counterfactual_equity_curve(
    curve: HistoricalMarketEquityCurve,
    outcomes: tuple[HistoricalDgeCounterfactualOutcome, ...],
) -> tuple[DailyEquityPoint, ...]:
    if not outcomes:
        return curve.points
    base_by_day = {point.timestamp: point.equity_usdt for point in curve.points}
    outcome_by_day: dict[datetime, Decimal] = {}
    for outcome in outcomes:
        day = _utc_day(outcome.outcome_observed_at) + timedelta(days=1)
        outcome_by_day[day] = outcome_by_day.get(day, ZERO) + outcome.net_pnl_usdt
    dates = sorted(set(base_by_day) | set(outcome_by_day))
    current_base = curve.points[0].equity_usdt
    cumulative_outcome = ZERO
    points: list[DailyEquityPoint] = []
    for day in dates:
        current_base = base_by_day.get(day, current_base)
        cumulative_outcome += outcome_by_day.get(day, ZERO)
        equity = current_base + cumulative_outcome
        if equity <= ZERO:
            raise ValueError("DGE_COUNTERFACTUAL_EQUITY_INVALID")
        points.append(DailyEquityPoint(day, equity))
    return tuple(points)


def _market_evidence_blockers(
    *,
    result: HistoricalReplayRunResult,
    market: VirtualMarket,
    cycles: tuple[HistoricalReplayCycleResult, ...],
    walk_forward_report: WalkForwardReport | None,
    robustness_report: BacktestRobustnessReport | None,
    reproducibility_reference_sha256: str | None,
    dge_blockers: tuple[str, ...],
) -> tuple[str, ...]:
    blockers: list[str] = list(dge_blockers)
    if walk_forward_report is None:
        blockers.append("WALK_FORWARD_EVIDENCE_MISSING")
    if robustness_report is None:
        blockers.append("ROBUSTNESS_EVIDENCE_MISSING")
    if reproducibility_reference_sha256 is None:
        blockers.append("DECISION_REPRODUCIBILITY_EVIDENCE_MISSING")
    elif reproducibility_reference_sha256 != result.semantic_result_sha256:
        blockers.append("DECISION_REPRODUCIBILITY_FAILED")
    if any(cycle.replay_snapshot.execution_context is None for cycle in cycles):
        blockers.append("EXECUTION_MODEL_EVIDENCE_MISSING")
    if any(position.market == market.value for position in result.open_positions):
        blockers.append("OPEN_POSITIONS_AT_REPLAY_END")
    return tuple(dict.fromkeys(blockers))


def _peak_margin_utilization(
    market: VirtualMarket,
    cycles: tuple[HistoricalReplayCycleResult, ...],
) -> Decimal | None:
    if market is VirtualMarket.SPOT:
        return None
    values = tuple(
        value
        for cycle in cycles
        for value in (
            cycle.portfolio_before.margin_utilization_ratio,
            cycle.portfolio_after.margin_utilization_ratio,
        )
        if value is not None
    )
    return max(values, default=ZERO)


def _performance_evaluation(
    *,
    market: VirtualMarket,
    cycles: tuple[HistoricalReplayCycleResult, ...],
    trades: tuple[VirtualClosedTradeRecord, ...],
    curve: HistoricalMarketEquityCurve,
    portfolio_performance: VirtualPortfolioPerformance,
    attribution: VirtualTradeAttributionLedger,
    reproducibility_rate: Decimal,
    peak_margin_utilization: Decimal | None,
) -> HistoricalMarketPerformanceEvaluation:
    ending = cycles[-1].portfolio_after
    wins = tuple(trade for trade in trades if trade.net_pnl_usdt > ZERO)
    losses = tuple(trade for trade in trades if trade.net_pnl_usdt < ZERO)
    gross_profit = sum((trade.net_pnl_usdt for trade in wins), ZERO)
    gross_loss = abs(sum((trade.net_pnl_usdt for trade in losses), ZERO))
    fees = sum((trade.fee_cost_usdt for trade in trades), ZERO)
    slippage = sum((trade.slippage_cost_usdt for trade in trades), ZERO)
    funding = sum((trade.funding_cost_usdt for trade in trades), ZERO)
    expectancy = _average(tuple(trade.net_pnl_usdt for trade in trades))
    win_rate = _ratio(len(wins), len(trades))
    profit_factor = gross_profit / gross_loss if gross_loss > ZERO else None
    average_win = _average(tuple(trade.net_pnl_usdt for trade in wins))
    average_loss = _average(tuple(abs(trade.net_pnl_usdt) for trade in losses))
    payoff = (
        average_win / average_loss
        if average_win is not None and average_loss is not None and average_loss != ZERO
        else None
    )
    max_drawdown_usdt = _max_drawdown_usdt(curve.points)
    recovery = (
        (ending.equity_usdt - ending.initial_equity_usdt) / max_drawdown_usdt
        if max_drawdown_usdt > ZERO
        else None
    )
    duration_seconds = max(
        1,
        int(
            (
                cycles[-1].replay_snapshot.created_at
                - cycles[0].replay_snapshot.created_at
            ).total_seconds()
        ),
    )
    holding_seconds = sum(
        (
            Decimal(int((trade.exit_time - trade.entry_time).total_seconds()))
            for trade in trades
        ),
        ZERO,
    )
    time_in_market = min(ONE, holding_seconds / Decimal(duration_seconds))
    utilization_values = tuple(
        _portfolio_utilization(market, cycle.portfolio_after) for cycle in cycles
    )
    common = (
        _metric("initial_equity", ending.initial_equity_usdt, "USDT"),
        _metric("ending_equity", ending.equity_usdt, "USDT"),
        _metric(
            "net_pnl_usdt",
            ending.equity_usdt - ending.initial_equity_usdt,
            "USDT",
        ),
        _metric("net_return_pct", portfolio_performance.net_return, "ratio"),
        _metric("gross_profit", gross_profit, "USDT"),
        _metric("gross_loss", gross_loss, "USDT"),
        _metric("fees_paid", fees, "USDT"),
        _metric("slippage_cost", slippage, "USDT"),
        _metric("spread_cost", None, "USDT"),
        _metric("turnover", _turnover(trades), "USDT"),
        _metric("trade_count", len(trades), "count"),
        _metric("winning_trades", len(wins), "count"),
        _metric("losing_trades", len(losses), "count"),
        _metric("win_rate", win_rate, "ratio"),
        _metric("profit_factor", profit_factor, "ratio"),
        _metric("expectancy_usdt", expectancy, "USDT"),
        _metric(
            "expectancy_pct",
            expectancy / ending.initial_equity_usdt if expectancy is not None else None,
            "ratio",
        ),
        _metric("average_win", average_win, "USDT"),
        _metric("average_loss", average_loss, "USDT"),
        _metric("payoff_ratio", payoff, "ratio"),
        _metric(
            "largest_win",
            max((trade.net_pnl_usdt for trade in wins), default=None),
            "USDT",
        ),
        _metric(
            "largest_loss",
            max((abs(trade.net_pnl_usdt) for trade in losses), default=None),
            "USDT",
        ),
        _metric("maximum_drawdown_usdt", max_drawdown_usdt, "USDT"),
        _metric("maximum_drawdown_pct", portfolio_performance.max_drawdown, "ratio"),
        _metric("drawdown_duration", _drawdown_duration(curve.points), "seconds"),
        _metric("recovery_factor", recovery, "ratio"),
        _metric("sharpe", portfolio_performance.portfolio_sharpe, "ratio"),
        _metric("sortino", portfolio_performance.portfolio_sortino, "ratio"),
        _metric(
            "calmar",
            portfolio_performance.annualized_return / portfolio_performance.max_drawdown
            if portfolio_performance.annualized_return is not None
            and portfolio_performance.max_drawdown > ZERO
            else None,
            "ratio",
        ),
        _metric("downside_deviation", None, "ratio"),
        _metric("return_volatility", None, "ratio"),
        _metric("consecutive_wins", _longest_streak(trades, winning=True), "count"),
        _metric("consecutive_losses", _longest_streak(trades, winning=False), "count"),
        _metric(
            "average_holding_period",
            holding_seconds / Decimal(len(trades)) if trades else None,
            "seconds",
        ),
        _metric("time_in_market", time_in_market, "ratio"),
        _metric("capital_utilization", _average(utilization_values), "ratio"),
        _metric(
            "mae",
            _average(tuple(trade.maximum_adverse_excursion for trade in trades)),
            "USDT",
        ),
        _metric(
            "mfe",
            _average(tuple(trade.maximum_favorable_excursion for trade in trades)),
            "USDT",
        ),
    )
    holds = sum(
        cycle.workflow.virtual_runtime_decision is None
        or cycle.workflow.virtual_runtime_decision.status.value == "NO_ACTION"
        for cycle in cycles
    )
    if market is VirtualMarket.SPOT:
        specific = _spot_metrics(cycles, trades, holds)
    else:
        specific = _futures_metrics(
            cycles,
            trades,
            holds,
            peak_margin_utilization or ZERO,
        )
    rejected = sum(
        cycle.workflow.virtual_runtime_request is not None
        and cycle.workflow.virtual_runtime_decision is not None
        and cycle.workflow.virtual_runtime_decision.status.value == "NO_ACTION"
        for cycle in cycles
    )
    partial_fills = sum(
        cycle.workflow.virtual_runtime_request is not None
        and cycle.workflow.virtual_runtime_decision is not None
        and cycle.workflow.virtual_runtime_decision.trade_intent is not None
        and cycle.workflow.virtual_runtime_decision.trade_intent.quantity
        < cycle.workflow.virtual_runtime_request.quantity
        for cycle in cycles
    )
    data_quality_failures = sum(
        str(cycle.replay_snapshot.snapshot.data_quality.value) != "DATA_VALID"
        for cycle in cycles
    )
    operational = (
        _metric(
            "data_quality_failure_rate",
            _ratio(data_quality_failures, len(cycles)),
            "ratio",
        ),
        _metric("no_trade_rate", _ratio(holds, len(cycles)), "ratio"),
        _metric(
            "hard_blocker_rate",
            _ratio(sum(bool(cycle.blockers) for cycle in cycles), len(cycles)),
            "ratio",
        ),
        _metric("execution_rejection_rate", _ratio(rejected, len(cycles)), "ratio"),
        _metric("partial_fill_rate", _ratio(partial_fills, len(cycles)), "ratio"),
        _metric(
            "average_slippage",
            slippage / Decimal(len(trades)) if trades else None,
            "USDT",
        ),
        _metric(
            "fee_drag",
            fees / ending.initial_equity_usdt,
            "ratio",
        ),
        _metric(
            "funding_drag",
            funding / ending.initial_equity_usdt,
            "ratio",
        ),
        _metric("deterministic_replay_match_rate", reproducibility_rate, "ratio"),
        _metric("event_duplicate_rate", ZERO, "ratio"),
        _metric("reconciliation_error_count", 0, "count"),
    )
    return HistoricalMarketPerformanceEvaluation(
        market=market,
        portfolio_performance=portfolio_performance,
        attribution_ledger=attribution,
        common_kpis=common,
        market_specific_kpis=specific,
        operational_kpis=operational,
    )


def _spot_metrics(
    cycles: tuple[HistoricalReplayCycleResult, ...],
    trades: tuple[VirtualClosedTradeRecord, ...],
    holds: int,
) -> tuple[HistoricalReplayMetric, ...]:
    portfolio = cycles[-1].portfolio_after
    buy_count = sum(
        cycle.workflow.virtual_runtime_decision is not None
        and cycle.workflow.virtual_runtime_decision.trade_intent is not None
        and cycle.workflow.virtual_runtime_decision.trade_intent.action.value == "BUY"
        for cycle in cycles
    )
    sell_count = len(trades)
    reservation_failures = sum(
        any("RESERV" in blocker for blocker in cycle.blockers) for cycle in cycles
    )
    unsupported_shorts = sum(
        any("SHORT" in blocker for blocker in cycle.blockers) for cycle in cycles
    )
    return (
        _metric("spot_buy_count", buy_count, "count"),
        _metric("spot_sell_count", sell_count, "count"),
        _metric("spot_hold_count", holds, "count"),
        _metric("spot_quote_cash", portfolio.cash_usdt, "USDT"),
        _metric(
            "spot_inventory_market_value",
            portfolio.equity_usdt - portfolio.cash_usdt,
            "USDT",
        ),
        _metric("spot_realized_pnl", portfolio.realized_pnl_usdt, "USDT"),
        _metric("spot_unrealized_pnl", portfolio.unrealized_pnl_usdt, "USDT"),
        _metric("spot_inventory_turnover", _turnover(trades), "USDT"),
        _metric(
            "spot_cash_utilization",
            _bounded_ratio(
                portfolio.equity_usdt - portfolio.cash_usdt,
                portfolio.equity_usdt,
            ),
            "ratio",
        ),
        _metric("spot_dust_value", None, "USDT"),
        _metric("spot_reservation_failures", reservation_failures, "count"),
        _metric("spot_unsupported_short_attempts", unsupported_shorts, "count"),
        _metric("spot_nav", portfolio.equity_usdt, "USDT"),
    )


def _futures_metrics(
    cycles: tuple[HistoricalReplayCycleResult, ...],
    trades: tuple[VirtualClosedTradeRecord, ...],
    holds: int,
    peak_margin_utilization: Decimal,
) -> tuple[HistoricalReplayMetric, ...]:
    portfolio = cycles[-1].portfolio_after
    long_trades = tuple(
        trade for trade in trades if trade.direction is TradeDirection.LONG
    )
    short_trades = tuple(
        trade for trade in trades if trade.direction is TradeDirection.SHORT
    )
    leverages = tuple(
        Decimal(portfolio_state.leverage)
        for cycle in cycles
        for portfolio_state in (cycle.portfolio_before, cycle.portfolio_after)
        if portfolio_state.leverage is not None
    )
    liquidation_trades = tuple(
        trade for trade in trades if trade.exit_reason is BacktestExitReason.LIQUIDATION
    )
    return (
        _metric("futures_long_count", len(long_trades), "count"),
        _metric("futures_short_count", len(short_trades), "count"),
        _metric("futures_close_count", len(trades), "count"),
        _metric("futures_hold_count", holds, "count"),
        _metric(
            "futures_long_pnl",
            sum((trade.net_pnl_usdt for trade in long_trades), ZERO),
            "USDT",
        ),
        _metric(
            "futures_short_pnl",
            sum((trade.net_pnl_usdt for trade in short_trades), ZERO),
            "USDT",
        ),
        _metric("futures_realized_pnl", portfolio.realized_pnl_usdt, "USDT"),
        _metric("futures_unrealized_pnl", portfolio.unrealized_pnl_usdt, "USDT"),
        _metric("futures_funding_pnl", -portfolio.funding_cost_usdt, "USDT"),
        _metric("futures_funding_drag", portfolio.funding_cost_usdt, "USDT"),
        _metric(
            "futures_margin_utilization",
            portfolio.margin_utilization_ratio or ZERO,
            "ratio",
        ),
        _metric(
            "futures_peak_margin_utilization",
            peak_margin_utilization,
            "ratio",
        ),
        _metric("futures_average_leverage", _average(leverages), "multiple"),
        _metric("futures_peak_leverage", max(leverages, default=None), "multiple"),
        _metric("futures_liquidation_count", len(liquidation_trades), "count"),
        _metric(
            "futures_liquidation_loss",
            abs(
                sum(
                    (trade.net_pnl_usdt for trade in liquidation_trades),
                    ZERO,
                )
            ),
            "USDT",
        ),
        _metric(
            "futures_position_reversal_count",
            sum(
                any("REVERS" in blocker for blocker in cycle.blockers)
                for cycle in cycles
            ),
            "count",
        ),
        _metric(
            "futures_reduce_only_rejection_count",
            sum(
                any("REDUCE_ONLY" in blocker for blocker in cycle.blockers)
                for cycle in cycles
            ),
            "count",
        ),
        _metric("futures_collateral_utilization", peak_margin_utilization, "ratio"),
    )


def _metric(
    metric_id: str,
    value: Decimal | int | None,
    unit: str,
) -> HistoricalReplayMetric:
    return HistoricalReplayMetric(
        metric_id=metric_id,
        value=value,
        unit=unit,
        supported=value is not None,
    )


def _average(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / Decimal(len(values))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator < 1:
        return ZERO
    return Decimal(numerator) / Decimal(denominator)


def _bounded_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= ZERO:
        return ZERO
    return min(ONE, max(ZERO, numerator / denominator))


def _turnover(trades: tuple[VirtualClosedTradeRecord, ...]) -> Decimal:
    return sum(
        ((trade.entry_price + trade.exit_price) * trade.quantity for trade in trades),
        ZERO,
    )


def _max_drawdown_usdt(points: tuple[DailyEquityPoint, ...]) -> Decimal:
    peak = points[0].equity_usdt
    maximum = ZERO
    for point in points:
        peak = max(peak, point.equity_usdt)
        maximum = max(maximum, peak - point.equity_usdt)
    return maximum


def _drawdown_duration(points: tuple[DailyEquityPoint, ...]) -> int:
    peak_time = points[0].timestamp
    peak = points[0].equity_usdt
    longest = 0
    for point in points:
        if point.equity_usdt >= peak:
            peak = point.equity_usdt
            peak_time = point.timestamp
        else:
            longest = max(longest, int((point.timestamp - peak_time).total_seconds()))
    return longest


def _longest_streak(
    trades: tuple[VirtualClosedTradeRecord, ...],
    *,
    winning: bool,
) -> int:
    longest = 0
    current = 0
    for trade in sorted(trades, key=lambda item: (item.exit_time, item.trade_id)):
        matches = trade.net_pnl_usdt > ZERO if winning else trade.net_pnl_usdt < ZERO
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def _portfolio_utilization(
    market: VirtualMarket,
    portfolio: VirtualPortfolioState,
) -> Decimal:
    if market is VirtualMarket.USD_M_FUTURES:
        return portfolio.margin_utilization_ratio or ZERO
    return _bounded_ratio(
        portfolio.equity_usdt - portfolio.cash_usdt,
        portfolio.equity_usdt,
    )


def _utc_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use canonical UTC")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{name} must be non-empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


__all__ = (
    "HistoricalDgeCounterfactualOutcome",
    "HistoricalMarketPerformanceEvaluation",
    "HistoricalMarketReplayEvaluation",
    "HistoricalReplayMetric",
    "HistoricalReplayPublication",
    "HistoricalReplaySystemEvaluation",
    "HistoricalReplaySystemEvaluator",
)

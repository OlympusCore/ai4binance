# ruff: noqa: E501

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.application.virtual_runtime_eligibility import (
    evaluate_virtual_simulation_eligibility as canonical_virtual_simulation_eligibility,
)
from ai4binance.application.virtual_runtime_performance import (
    calculate_virtual_portfolio_performance_metrics,
)
from ai4binance.domain import Action, ValidationStatus
from ai4binance.enterprise import GpuTelemetryAssessment
from ai4binance.governance.blocker_reduction import VirtualBlockerReduction
from ai4binance.governance.dge_models import DgeDecisionStatus
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.ops.continuous_assurance import (
    TrustAssuranceBundle,
    TrustAssuranceResult,
    UncertaintyLevel,
)
from ai4binance.ops.decision_telemetry import DgeEffectivenessMetrics, EvidenceQuality
from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy, PositionExposure
from ai4binance.research import virtual_runtime as research_virtual_runtime
from ai4binance.research.backtesting.liquidity import LiquidityStressConfig
from ai4binance.research.backtesting.models import BacktestExitReason
from ai4binance.research.backtesting.robustness import (
    BacktestRobustnessReport,
    BootstrapAssessment,
    StressResult,
    StressScenario,
)
from ai4binance.research.equity_metrics import (
    EquityObservation,
    calculate_annualized_return,
    calculate_equity_max_drawdown,
    calculate_equity_returns,
    calculate_periodic_sharpe,
    calculate_periodic_sortino,
    calculate_regular_sample_seconds,
)
from ai4binance.research.virtual_market import (
    AcceptanceStatus,
    DailyEquityPoint,
    MarketAcceptanceResult,
    SystemResearchAcceptance,
    VirtualMarket,
)
from ai4binance.research.virtual_runtime import (
    IndependentVirtualPortfolios,
    VirtualEvidenceSurfaceAdapter,
    VirtualExitContext,
    VirtualFuturesPositionContext,
    VirtualImprovementResearchQueue,
    VirtualManagedPosition,
    VirtualMarketRuntime,
    VirtualNoTradeEvidenceSurface,
    VirtualPortfolioPerformance,
    VirtualPortfolioRiskGovernor,
    VirtualPortfolioState,
    VirtualPositionLifecycleStatus,
    VirtualPositionSide,
    VirtualResearchEvidenceSurface,
    VirtualRuntimeDecisionStatus,
    VirtualRuntimeRequest,
    VirtualStagedImprovementCandidate,
)
from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPortfolioState as PortfolioStateModuleVirtualPortfolioState,
)
from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPositionSide as PortfolioStateModuleVirtualPositionSide,
)
from ai4binance.research.virtual_runtime_portfolios import (
    IndependentVirtualPortfolios as PortfoliosModuleIndependentVirtualPortfolios,
)
from ai4binance.research.virtual_runtime_request import (
    VirtualRuntimeRequest as RequestModuleVirtualRuntimeRequest,
)
from ai4binance.research.virtual_runtime_risk import (
    VirtualPortfolioRiskGovernor as RiskModuleVirtualPortfolioRiskGovernor,
)
from ai4binance.research.virtual_runtime_trade_intent import (
    VirtualTradeIntent as TradeIntentModuleVirtualTradeIntent,
)
from ai4binance.research_governance import VirtualImprovementNextCandidateIntakeHandoff
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 3, 1, tzinfo=UTC)
legacy_virtual_simulation_eligibility = cast(
    Any,
    research_virtual_runtime,
)._evaluate_virtual_simulation_eligibility_legacy


def approved_virtual_runtime_request(**kwargs: object) -> VirtualRuntimeRequest:
    values = {
        "dge_decision": DgeDecisionStatus.APPROVED_PAPER_ONLY.value,
        "dge_simulation_allowed": True,
        **kwargs,
    }
    return RequestModuleVirtualRuntimeRequest(**cast(Any, values))


def test_virtual_runtime_risk_governor_is_reexported_by_compatibility_facade() -> None:
    assert VirtualPortfolioRiskGovernor is RiskModuleVirtualPortfolioRiskGovernor
    assert VirtualPortfolioRiskGovernor().maximum_futures_leverage == 5


def test_virtual_runtime_portfolio_state_is_reexported_by_compatibility_facade() -> (
    None
):
    assert VirtualPortfolioState is PortfolioStateModuleVirtualPortfolioState
    assert VirtualPositionSide is PortfolioStateModuleVirtualPositionSide


def test_independent_virtual_portfolios_is_reexported_by_compatibility_facade() -> None:
    assert IndependentVirtualPortfolios is PortfoliosModuleIndependentVirtualPortfolios


def test_virtual_runtime_request_is_reexported_by_compatibility_facade() -> None:
    assert VirtualRuntimeRequest is RequestModuleVirtualRuntimeRequest


def test_virtual_runtime_trade_intent_is_reexported_by_compatibility_facade() -> None:
    assert (
        research_virtual_runtime.VirtualTradeIntent
        is TradeIntentModuleVirtualTradeIntent
    )


def lifecycle_candle(
    offset: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> OHLCVCandle:
    return OHLCVCandle(
        NOW + timedelta(hours=offset),
        Decimal(open_price),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        Decimal("1000"),
    )


def equity_point(offset_days: int, equity: str) -> DailyEquityPoint:
    return DailyEquityPoint(
        NOW + timedelta(days=offset_days),
        Decimal(equity),
    )


def open_virtual_position() -> VirtualManagedPosition:
    return VirtualManagedPosition(
        position_id="virtual-position-1",
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        market="SPOT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.2"),
        initial_quantity=Decimal("2"),
        remaining_quantity=Decimal("2"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        atr=Decimal("2"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        take_profit_quantity_ratios=(Decimal("0.5"), Decimal("0.5")),
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0.0005"),
        tick_size=Decimal("0.1"),
    )


def attributed_open_virtual_position() -> VirtualManagedPosition:
    return VirtualManagedPosition(
        position_id="virtual-position-attrib",
        candidate_id="candidate-attrib",
        symbol="HOTUSDT",
        market="SPOT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.2"),
        initial_quantity=Decimal("2"),
        remaining_quantity=Decimal("2"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        atr=Decimal("2"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        take_profit_quantity_ratios=(Decimal("0.5"), Decimal("0.5")),
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0.0005"),
        tick_size=Decimal("0.1"),
        strategy_id="breakout",
        strategy_version="2026.08",
        strategy_config_version="cfg-3",
        strategy_config_hash="hash-abc",
        regime="TREND",
        timeframe="1h",
        snapshot_id="snapshot:attrib:1",
        decision_id="dge:attrib:1",
        dge_decision="ALLOW_VIRTUAL",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY", "HTF_CONFLUENCE"),
        entry_slippage_cost_usdt=Decimal("0.3"),
        funding_cost_usdt=Decimal("0"),
    )


def research_surface_for_staging(
    snapshot_id: str = "snapshot:stage:research:1",
) -> VirtualResearchEvidenceSurface:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id=f"virtual:spot:{snapshot_id}",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing: Any = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning: Any = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id=f"virtual-position-{snapshot_id}",
            candidate_id=f"candidate:{snapshot_id}",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert losing is not None
    assert winning is not None
    ledger = VirtualMarketRuntime.build_trade_attribution_ledger((losing, winning))
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=(
            equity_point(0, "1000"),
            equity_point(1, "1015"),
            equity_point(2, "1025"),
            equity_point(3, "1040"),
        ),
    )
    walk_forward_report: Any = SimpleNamespace(
        report_id=f"wf:{snapshot_id}",
        blockers=(),
        folds=(),
    )
    robustness = BacktestRobustnessReport(
        stress_results=(
            StressResult(
                scenario=StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
                net_return=0.04,
                profit_factor=1.4,
                expectancy_usdt=4.0,
                max_drawdown=0.05,
                trade_count=2,
                delta_net_return=0.0,
                delta_profit_factor=0.0,
                delta_expectancy_usdt=0.0,
                delta_max_drawdown=0.0,
                delta_trade_count=0,
                spread_cost_usdt=0.5,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
            StressResult(
                scenario=StressScenario(
                    "COST_1_5X", Decimal("0.0015"), Decimal("0.00075")
                ),
                net_return=0.03,
                profit_factor=1.3,
                expectancy_usdt=3.0,
                max_drawdown=0.05,
                trade_count=2,
                delta_net_return=-0.01,
                delta_profit_factor=-0.1,
                delta_expectancy_usdt=-1.0,
                delta_max_drawdown=0.0,
                delta_trade_count=0,
                spread_cost_usdt=0.75,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
            StressResult(
                scenario=StressScenario("COST_2X", Decimal("0.002"), Decimal("0.001")),
                net_return=0.02,
                profit_factor=1.2,
                expectancy_usdt=2.0,
                max_drawdown=0.06,
                trade_count=2,
                delta_net_return=-0.02,
                delta_profit_factor=-0.2,
                delta_expectancy_usdt=-2.0,
                delta_max_drawdown=0.01,
                delta_trade_count=0,
                spread_cost_usdt=1.0,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
        ),
        bootstrap=BootstrapAssessment(
            simulations=1000,
            seed=42,
            probability_of_loss=0.20,
            median_net_return=0.03,
            p05_net_return=-0.01,
            p95_max_drawdown=0.10,
        ),
        blockers=(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=2,
        intervention_count=0,
        protective_block_count=0,
        false_block_count=0,
        loss_avoided_usdt=Decimal("0"),
        profit_missed_usdt=Decimal("0"),
        drawdown_without_dge_pct=Decimal("0.04"),
        drawdown_with_dge_pct=Decimal("0.04"),
        counterfactual_expectancy_delta_usdt=Decimal("0"),
        computed_at=NOW,
    )
    return VirtualMarketRuntime.build_research_evidence_surface(
        session_id=snapshot_id,
        portfolio_id=f"virtual:spot:{snapshot_id}",
        generation=1,
        configured_start_at=NOW - timedelta(days=400),
        feature_warmup_start=NOW - timedelta(days=430),
        last_replayed_at=NOW,
        market="SPOT",
        timeframe="1h",
        portfolio_performance=performance,
        attribution_ledger=ledger,
        walk_forward_report=walk_forward_report,
        robustness_report=robustness,
        dge_metrics=dge_metrics,
        replay_state_hash=f"hash:{snapshot_id}",
        observed_at=NOW,
    )


def test_virtual_simulation_eligibility_stays_separate_from_order_authority() -> None:
    eligibility = canonical_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
    )

    assert eligibility.eligible is True
    assert eligibility.virtual_simulation_allowed is True
    assert eligibility.auto_simulation_allowed is True
    assert eligibility.binance_order_allowed is False
    assert eligibility.live_order_allowed is False
    assert eligibility.requires_manual_confirmation is False


def test_virtual_simulation_eligibility_blocks_non_virtual_surface() -> None:
    eligibility = canonical_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.BINANCE_MARKET,
    )

    assert eligibility.eligible is False
    assert "EXECUTION_SURFACE_NOT_VIRTUAL_MARKET" in eligibility.blockers
    assert eligibility.binance_order_allowed is False
    assert eligibility.live_order_allowed is False
    assert eligibility.blocker_reduction is not None
    reduction = cast(VirtualBlockerReduction, eligibility.blocker_reduction)
    assert reduction.root_cause_codes == eligibility.blockers


def test_legacy_virtual_simulation_eligibility_wrapper_matches_canonical_helper() -> (
    None
):
    legacy = legacy_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        analysis_blockers=("ANALYSIS_BLOCKER",),
        risk_blockers=("RISK_BLOCKER",),
    )
    canonical = canonical_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        analysis_blockers=("ANALYSIS_BLOCKER",),
        risk_blockers=("RISK_BLOCKER",),
    )

    assert legacy == canonical
    assert legacy.eligible is False
    assert legacy.blockers == ("ANALYSIS_BLOCKER", "RISK_BLOCKER")


def test_virtual_market_runtime_runs_without_wallet_or_futures_account_services() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:1",
            decision_id="dge:1",
            candidate_id="candidate:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.trade_intent is not None
    assert decision.portfolio_before.open_position_count == 0
    assert decision.portfolio_after.open_position_count == 1
    assert decision.portfolio_after.cash_usdt == Decimal("900")
    assert decision.portfolio_after.inventory_quantity == Decimal("1")
    assert decision.portfolio_after.inventory_cost_basis_usdt == Decimal("100")
    assert decision.portfolio_after.realized_pnl_usdt == Decimal("0")
    assert decision.portfolio_after.unrealized_pnl_usdt == Decimal("0")


def test_virtual_market_runtime_fail_closes_default_unknown_dge_without_mutation() -> (
    None
):
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:dge:unknown",
        market="SPOT",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )
    request = RequestModuleVirtualRuntimeRequest(
        snapshot_id="snapshot:dge:unknown",
        decision_id="dge:unknown",
        candidate_id="candidate:dge:unknown",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        portfolio=portfolio,
    )

    first = runtime.evaluate(request)
    second = runtime.evaluate(request)

    assert request.dge_blockers == ("DGE_SIMULATION_NOT_APPROVED",)
    assert first == second
    assert first.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert first.portfolio_before == portfolio
    assert first.portfolio_after == portfolio
    assert first.trade_intent is None


@pytest.mark.parametrize(
    "dge_status",
    tuple(
        status
        for status in DgeDecisionStatus
        if status is not DgeDecisionStatus.APPROVED_PAPER_ONLY
    ),
)
def test_virtual_market_runtime_rejects_every_non_approved_paper_dge_status(
    dge_status: DgeDecisionStatus,
) -> None:
    portfolio = VirtualPortfolioState(
        portfolio_id=f"virtual:spot:dge:{dge_status.value.lower()}",
        market="SPOT",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )
    decision = VirtualMarketRuntime().evaluate(
        RequestModuleVirtualRuntimeRequest(
            snapshot_id=f"snapshot:dge:{dge_status.value.lower()}",
            decision_id=f"dge:{dge_status.value.lower()}",
            candidate_id=f"candidate:dge:{dge_status.value.lower()}",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            portfolio=portfolio,
            dge_decision=dge_status.value,
            dge_simulation_allowed=True,
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert decision.eligibility.blockers == ("DGE_SIMULATION_NOT_APPROVED",)
    assert decision.portfolio_after == portfolio
    assert decision.trade_intent is None


def test_virtual_market_runtime_preserves_stable_dge_blocker_stage_order() -> None:
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:dge:stable-blockers",
        market="SPOT",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:dge:stable-blockers",
        decision_id="dge:stable-blockers",
        candidate_id="candidate:dge:stable-blockers",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        portfolio=portfolio,
        risk_blockers=("RISK.VETO",),
        validation_blockers=("VAL.OOS_NOT_VALIDATED",),
        dge_blockers=("DGE_SIMULATION_NOT_APPROVED",),
    )

    first = VirtualMarketRuntime().evaluate(request)
    second = VirtualMarketRuntime().evaluate(request)

    assert first == second
    assert first.eligibility.blockers == (
        "RISK.VETO",
        "VAL.OOS_NOT_VALIDATED",
        "DGE_SIMULATION_NOT_APPROVED",
    )
    assert first.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert first.portfolio_after == portfolio
    assert first.trade_intent is None


def test_virtual_runtime_request_rejects_non_boolean_dge_allowance() -> None:
    with pytest.raises(
        ValueError,
        match="DGE simulation allowance must be boolean",
    ):
        approved_virtual_runtime_request(
            snapshot_id="snapshot:dge:invalid-allowance",
            decision_id="dge:invalid-allowance",
            candidate_id="candidate:dge:invalid-allowance",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:dge:invalid-allowance",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
            dge_simulation_allowed=cast(Any, 1),
        )


def test_virtual_market_runtime_rejects_market_mismatch_between_request_and_portfolio() -> (
    None
):
    runtime = VirtualMarketRuntime()

    with pytest.raises(
        ValueError,
        match="virtual runtime request market must match portfolio market",
    ):
        runtime.evaluate(
            approved_virtual_runtime_request(
                snapshot_id="snapshot:1",
                decision_id="dge:1",
                candidate_id="candidate:1",
                symbol="HOTUSDT",
                market="USD_M_FUTURES",
                action=Action.BUY,
                quantity=Decimal("1"),
                entry_price=Decimal("100"),
                stop_loss=Decimal("95"),
                take_profit_levels=(Decimal("110"),),
                portfolio=VirtualPortfolioState(
                    portfolio_id="virtual:spot:1",
                    market="SPOT",
                    cash_usdt=Decimal("1000"),
                    equity_usdt=Decimal("1000"),
                ),
            )
        )


def test_virtual_trade_intent_rejects_unsupported_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual trade intent market must be SPOT or USD_M_FUTURES",
    ):
        research_virtual_runtime.VirtualTradeIntent(
            snapshot_id="snapshot:1",
            decision_id="dge:1",
            candidate_id="candidate:1",
            symbol="HOTUSDT",
            market="OPTIONS",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            reason_codes=("TEST",),
        )


def test_virtual_market_runtime_fail_closes_when_capacity_is_exhausted() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:1",
            decision_id="dge:1",
            candidate_id="candidate:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
                open_position_count=1,
                max_concurrent_positions=1,
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "PORTFOLIO_CAPACITY_EXCEEDED" in decision.eligibility.blockers


def test_virtual_market_runtime_rejects_spot_sell_without_inventory() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:1",
            decision_id="dge:1",
            candidate_id="candidate:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            take_profit_levels=(Decimal("90"),),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "SPOT_INVENTORY_INSUFFICIENT" in decision.eligibility.blockers


def test_virtual_market_runtime_realizes_spot_sell_pnl_without_cross_market_transfer() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:2",
            decision_id="dge:2",
            candidate_id="candidate:2",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("120"),
            stop_loss=Decimal("125"),
            take_profit_levels=(Decimal("100"),),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:2",
                market="SPOT",
                cash_usdt=Decimal("900"),
                equity_usdt=Decimal("1020"),
                inventory_quantity=Decimal("1"),
                inventory_cost_basis_usdt=Decimal("100"),
                open_position_count=1,
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.portfolio_after.cash_usdt == Decimal("1020")
    assert decision.portfolio_after.inventory_quantity == Decimal("0")
    assert decision.portfolio_after.inventory_cost_basis_usdt == Decimal("0")
    assert decision.portfolio_after.realized_pnl_usdt == Decimal("20")
    assert decision.portfolio_after.open_position_count == 0
    assert decision.portfolio_after.market == "SPOT"


def test_virtual_market_runtime_applies_partial_fill_spread_and_liquidity_impact() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:liq:1",
            decision_id="dge:liq:1",
            candidate_id="candidate:liq:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            half_spread_ratio=Decimal("0.0005"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.01"),
            candle_volume=Decimal("500"),
            liquidity_stress=LiquidityStressConfig(
                max_volume_participation=Decimal("0.01")
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:liq:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.trade_intent is not None
    assert decision.trade_intent.quantity == Decimal("5.00")
    assert decision.trade_intent.entry_price == Decimal("100.15")
    assert "ENTRY_PARTIALLY_FILLED" in decision.trade_intent.reason_codes
    assert decision.portfolio_after.cash_usdt == Decimal("499.2500")
    assert decision.portfolio_after.inventory_quantity == Decimal("5.00")
    assert decision.portfolio_after.slippage_cost_usdt == Decimal("0.7500")


def test_virtual_market_runtime_rejects_liquidity_fill_below_minimum_notional() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:liq:2",
            decision_id="dge:liq:2",
            candidate_id="candidate:liq:2",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("10"),
            entry_price=Decimal("10"),
            stop_loss=Decimal("9"),
            take_profit_levels=(Decimal("12"),),
            minimum_notional=Decimal("20"),
            candle_volume=Decimal("10"),
            liquidity_stress=LiquidityStressConfig(
                max_volume_participation=Decimal("0.01"),
                minimum_fill_ratio=Decimal("0.25"),
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:liq:2",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "LIQUIDITY_PARTIAL_FILL_BELOW_MINIMUM" in decision.eligibility.blockers
    assert "MIN_NOTIONAL_NOT_REACHED" in decision.eligibility.blockers


def test_virtual_market_runtime_blocks_entry_on_portfolio_governor_exposure_and_risk() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:gov:1",
            decision_id="dge:gov:1",
            candidate_id="candidate:gov:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("2"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            strategy_id="trend",
            correlation_group="alts",
            current_exposures=(
                PositionExposure("HOTUSDT", "trend", "alts", Decimal("180")),
            ),
            portfolio_governor=VirtualPortfolioRiskGovernor(
                exposure_policy=PortfolioRiskPolicy(
                    maximum_gross_usdt=Decimal("200"),
                    maximum_symbol_usdt=Decimal("150"),
                    maximum_correlation_group_usdt=Decimal("150"),
                    maximum_strategy_usdt=Decimal("150"),
                ),
                maximum_risk_per_trade_usdt=Decimal("8"),
                maximum_open_risk_usdt=Decimal("15"),
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:gov:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
                current_open_risk_usdt=Decimal("10"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "PORTFOLIO_GROSS_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "SYMBOL_EXPOSURE_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "CORRELATION_GROUP_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "STRATEGY_EXPOSURE_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "VIRTUAL_RISK_PER_TRADE_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "VIRTUAL_OPEN_RISK_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert decision.blocker_reduction is not None
    assert decision.blocker_reduction.root_cause_codes == decision.eligibility.blockers
    assert decision.blocker_reduction.has_unknown_classifications is True


def test_virtual_market_runtime_blocks_entry_on_drawdown_and_loss_streak_limits() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:gov:2",
            decision_id="dge:gov:2",
            candidate_id="candidate:gov:2",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            portfolio_governor=VirtualPortfolioRiskGovernor(
                maximum_drawdown_ratio=Decimal("0.10"),
                maximum_consecutive_losses=2,
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:gov:2",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
                max_drawdown_ratio=Decimal("0.12"),
                consecutive_losses=2,
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert decision.halted is True
    assert decision.halt_review is not None
    assert "VIRTUAL_DRAWDOWN_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert decision.halt_review.trigger_blocker == "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED"
    assert decision.halt_review.status.value == "ACTIVE"
    assert decision.halt_review.consecutive_losses == 2
    assert decision.halt_review.maximum_consecutive_losses == 2
    assert decision.halt_review.improvement_candidates[0].candidate_id.startswith(
        "improvement:loss-streak:"
    )
    assert (
        decision.halt_review.reset_criteria[0]
        == "Resume only when a later request supplies `portfolio.consecutive_losses < maximum_consecutive_losses`."
    )


def test_virtual_market_runtime_processes_staged_spot_exit_lifecycle() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:lifecycle:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )

    partial = runtime.process_position(
        position=open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "111", "99", "108"),
    )
    closed = runtime.process_position(
        position=partial.position_after,
        portfolio=partial.portfolio_after,
        candle=lifecycle_candle(2, "108", "121", "106", "118"),
        context=VirtualExitContext(ignored_signals=2, htf_weakness=True),
    )

    assert (
        partial.position_after.status is VirtualPositionLifecycleStatus.PARTIALLY_CLOSED
    )
    assert partial.position_after.remaining_quantity == Decimal("1.0")
    assert partial.position_after.next_target_index == 1
    assert partial.position_after.trailing_stop == Decimal("105.0")
    assert partial.exit_reason is BacktestExitReason.TARGET
    assert closed.position_after.status is VirtualPositionLifecycleStatus.CLOSED
    assert closed.position_after.remaining_quantity == Decimal("0.0")
    assert len(closed.position_after.exits) == 2
    assert closed.position_after.closure_review is not None
    assert closed.position_after.closure_review.exit_reason is BacktestExitReason.TARGET
    assert closed.position_after.closure_review.ignored_signals == 2
    assert closed.position_after.closure_review.htf_weakness is True
    assert closed.portfolio_after.open_position_count == 0
    assert closed.portfolio_after.cash_usdt > Decimal("1029")


def test_virtual_market_runtime_materializes_managed_position_from_request_lineage() -> (
    None
):
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:materialize:1",
        decision_id="dge:materialize:1",
        candidate_id="candidate:materialize:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0.0005"),
        half_spread_ratio=Decimal("0.0005"),
        strategy_id="trend",
        strategy_version="2026.08",
        strategy_config_version="cfg-2",
        strategy_config_hash="hash-trend",
        regime="TREND",
        timeframe="15m",
        dge_decision=DgeDecisionStatus.APPROVED_PAPER_ONLY.value,
        risk_policy_version="risk-v1",
        validation_version="validation-v2",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:materialize:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )

    decision = runtime.evaluate(request)
    position = VirtualMarketRuntime.materialize_managed_position(
        request=request,
        decision=decision,
        opened_at=NOW,
    )

    assert position.strategy_id == "trend"
    assert position.strategy_version == "2026.08"
    assert position.strategy_config_hash == "hash-trend"
    assert position.regime == "TREND"
    assert position.timeframe == "15m"
    assert position.snapshot_id == "snapshot:materialize:1"
    assert position.decision_id == "dge:materialize:1"
    assert position.dge_decision == DgeDecisionStatus.APPROVED_PAPER_ONLY.value
    assert position.risk_policy_version == "risk-v1"
    assert position.validation_version == "validation-v2"
    assert position.entry_reason == ("BREAKOUT_ENTRY",)
    assert position.entry_slippage_cost_usdt == Decimal("0.1")


def test_virtual_market_runtime_applies_breakeven_and_trailing_exit() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:lifecycle:2",
        market="SPOT",
        cash_usdt=Decimal("900"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("1"),
        inventory_cost_basis_usdt=Decimal("100"),
        open_position_count=1,
    )
    position = VirtualManagedPosition(
        position_id="virtual-position-2",
        candidate_id="candidate-2",
        symbol="HOTUSDT",
        market="SPOT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.1"),
        initial_quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        atr=Decimal("2"),
        take_profit_levels=(Decimal("120"),),
        breakeven_trigger_r=Decimal("0.4"),
        trailing_atr_multiple=Decimal("0.5"),
        tick_size=Decimal("0.1"),
    )

    moved = runtime.process_position(
        position=position,
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "99", "102"),
    )
    closed = runtime.process_position(
        position=moved.position_after,
        portfolio=moved.portfolio_after,
        candle=lifecycle_candle(2, "102", "103", "100.9", "101"),
        context=VirtualExitContext(volatility_expansion=True, level_break=True),
    )

    assert moved.position_after.trailing_stop == Decimal("101.0")
    assert closed.exit_reason is BacktestExitReason.TRAILING_STOP
    assert closed.position_after.closure_review is not None
    assert closed.position_after.closure_review.trailing_quality == "PROTECTIVE"
    assert closed.position_after.closure_review.volatility_expansion is True
    assert closed.position_after.closure_review.level_break is True


def test_virtual_market_runtime_emits_closed_trade_with_full_attribution() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:attrib:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )

    closed = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    )

    assert closed.closed_trade is not None
    trade = closed.closed_trade
    assert trade.attribution.strategy_id == "breakout"
    assert trade.attribution.strategy_version == "2026.08"
    assert trade.attribution.strategy_config_hash == "hash-abc"
    assert trade.attribution.market == "SPOT"
    assert trade.attribution.symbol == "HOTUSDT"
    assert trade.attribution.regime == "TREND"
    assert trade.attribution.timeframe == "1h"
    assert trade.attribution.snapshot_id == "snapshot:attrib:1"
    assert trade.attribution.decision_id == "dge:attrib:1"
    assert trade.dge_decision == "ALLOW_VIRTUAL"
    assert trade.risk_policy_version == "risk-v2"
    assert trade.validation_version == "validation-v5"
    assert trade.entry_reason == ("BREAKOUT_ENTRY", "HTF_CONFLUENCE")
    assert trade.exit_reason is BacktestExitReason.HARD_STOP
    assert trade.false_breakout is True
    assert trade.slippage_cost_usdt == Decimal("0.3")


def test_virtual_market_runtime_builds_strategy_and_regime_attribution_ledger() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:attrib:2",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-attrib-2",
            candidate_id="candidate-attrib-2",
            strategy_id="mean_revert",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade

    assert losing is not None
    assert winning is not None

    ledger = VirtualMarketRuntime.build_trade_attribution_ledger((losing, winning))

    assert len(ledger.by_strategy) == 2
    assert len(ledger.by_regime) == 2
    assert len(ledger.by_strategy_regime) == 2
    breakout_view = next(
        view for view in ledger.by_strategy if view.strategy_id == "breakout"
    )
    trend_view = next(view for view in ledger.by_regime if view.regime == "TREND")
    range_combo = next(
        view
        for view in ledger.by_strategy_regime
        if view.strategy_id == "mean_revert" and view.regime == "RANGE"
    )
    assert breakout_view.trade_count == 1
    assert breakout_view.false_breakout_rate == Decimal("1.0")
    assert breakout_view.drawdown_contribution_usdt > Decimal("0")
    assert trend_view.expectancy_usdt < Decimal("0")
    assert range_combo.net_pnl_usdt > Decimal("0")
    assert ledger.trade_edge_ledger.by_strategy[0].trade_count == 1


def test_virtual_market_runtime_builds_research_evidence_surface() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:surface:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-attrib-3",
            candidate_id="candidate-attrib-3",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert losing is not None
    assert winning is not None
    ledger = VirtualMarketRuntime.build_trade_attribution_ledger((losing, winning))
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=(
            equity_point(0, "1000"),
            equity_point(1, "1015"),
            equity_point(2, "1025"),
            equity_point(3, "1040"),
        ),
    )
    walk_forward_report: Any = SimpleNamespace(
        report_id="wf:surface:1",
        blockers=(),
        folds=(
            SimpleNamespace(
                oos_result=SimpleNamespace(
                    trades=(
                        SimpleNamespace(net_pnl_usdt=Decimal("12")),
                        SimpleNamespace(net_pnl_usdt=Decimal("6")),
                    )
                )
            ),
        ),
    )
    robustness = BacktestRobustnessReport(
        stress_results=(
            StressResult(
                scenario=StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
                net_return=0.04,
                profit_factor=1.4,
                expectancy_usdt=4.0,
                max_drawdown=0.05,
                trade_count=2,
                delta_net_return=0.0,
                delta_profit_factor=0.0,
                delta_expectancy_usdt=0.0,
                delta_max_drawdown=0.0,
                delta_trade_count=0,
                spread_cost_usdt=0.5,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
            StressResult(
                scenario=StressScenario(
                    "COST_1_5X", Decimal("0.0015"), Decimal("0.00075")
                ),
                net_return=0.03,
                profit_factor=1.3,
                expectancy_usdt=3.0,
                max_drawdown=0.06,
                trade_count=2,
                delta_net_return=-0.01,
                delta_profit_factor=-0.1,
                delta_expectancy_usdt=-1.0,
                delta_max_drawdown=0.01,
                delta_trade_count=0,
                spread_cost_usdt=0.75,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
            StressResult(
                scenario=StressScenario("COST_2X", Decimal("0.002"), Decimal("0.001")),
                net_return=0.02,
                profit_factor=1.2,
                expectancy_usdt=2.0,
                max_drawdown=0.07,
                trade_count=2,
                delta_net_return=-0.02,
                delta_profit_factor=-0.2,
                delta_expectancy_usdt=-2.0,
                delta_max_drawdown=0.02,
                delta_trade_count=0,
                spread_cost_usdt=1.0,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
        ),
        bootstrap=BootstrapAssessment(
            simulations=1000,
            seed=42,
            probability_of_loss=0.20,
            median_net_return=0.03,
            p05_net_return=-0.01,
            p95_max_drawdown=0.10,
        ),
        blockers=(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=2,
        intervention_count=0,
        protective_block_count=0,
        false_block_count=0,
        loss_avoided_usdt=Decimal("0"),
        profit_missed_usdt=Decimal("0"),
        drawdown_without_dge_pct=Decimal("0.04"),
        drawdown_with_dge_pct=Decimal("0.04"),
        counterfactual_expectancy_delta_usdt=Decimal("0"),
        computed_at=NOW,
    )

    surface = VirtualMarketRuntime.build_research_evidence_surface(
        session_id="snapshot:surface:1",
        portfolio_id="virtual:spot:surface:1",
        generation=1,
        configured_start_at=NOW - timedelta(days=400),
        feature_warmup_start=NOW - timedelta(days=430),
        last_replayed_at=NOW,
        market="SPOT",
        timeframe="1h",
        portfolio_performance=performance,
        attribution_ledger=ledger,
        walk_forward_report=walk_forward_report,
        robustness_report=robustness,
        dge_metrics=dge_metrics,
        replay_state_hash="hash-surface-1",
        observed_at=NOW,
    )

    assert isinstance(surface, VirtualResearchEvidenceSurface)
    assert surface.market_performance.oos_expectancy_usdt == Decimal("9")
    assert len(surface.market_performance.cost_stress_evidence) == 3
    assert len(surface.market_performance.regime_attribution) == 2
    assert "TRADE_SAMPLE_INSUFFICIENT" in surface.blockers
    assert len(surface.improvement_candidates) == 1
    candidate = surface.improvement_candidates[0]
    assert candidate.affected_regimes == ("TREND", "RANGE")
    assert candidate.execution_allowed is False
    assert surface.performance_snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert (
        surface.performance_snapshot.improvement_candidates[0].candidate_id
        == candidate.candidate_id
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)
    payload: Any = VirtualMarketRuntime.evidence_surface_payload(adapter)
    metric_summary = payload["telemetry_metric_summary"]
    assert metric_summary["virtual.completed_trades"]["value"] == "2"
    closed_trades: tuple[Any, Any] = (losing, winning)
    expected_profit_factor = sum(
        trade.net_pnl_usdt
        for trade in closed_trades
        if trade.net_pnl_usdt > Decimal("0")
    ) / abs(
        sum(
            trade.net_pnl_usdt
            for trade in closed_trades
            if trade.net_pnl_usdt < Decimal("0")
        )
    )
    assert metric_summary["virtual.profit_factor"]["value"] == str(
        expected_profit_factor
    )
    assert metric_summary["virtual.win_rate"]["value"] == "0.5"
    assert metric_summary["virtual.average_r"]["unit"] == "R"


def test_virtual_market_runtime_surfaces_dge_counterfactual_effectiveness() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:dge:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-attrib-4",
            candidate_id="candidate-attrib-4",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert losing is not None
    assert winning is not None
    ledger = VirtualMarketRuntime.build_trade_attribution_ledger((losing, winning))
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=(
            equity_point(0, "1000"),
            equity_point(1, "1015"),
            equity_point(2, "1025"),
            equity_point(3, "1040"),
        ),
    )
    walk_forward_report: Any = SimpleNamespace(
        report_id="wf:dge:1",
        blockers=("DGE_PROTECTIVE_BLOCK",),
        folds=(),
    )
    robustness = BacktestRobustnessReport(
        stress_results=(
            StressResult(
                scenario=StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
                net_return=0.04,
                profit_factor=1.4,
                expectancy_usdt=4.0,
                max_drawdown=0.05,
                trade_count=2,
                delta_net_return=0.0,
                delta_profit_factor=0.0,
                delta_expectancy_usdt=0.0,
                delta_max_drawdown=0.0,
                delta_trade_count=0,
                spread_cost_usdt=0.5,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
        ),
        bootstrap=BootstrapAssessment(
            simulations=1000,
            seed=42,
            probability_of_loss=0.20,
            median_net_return=0.03,
            p05_net_return=-0.01,
            p95_max_drawdown=0.10,
        ),
        blockers=(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=6,
        intervention_count=3,
        protective_block_count=2,
        false_block_count=1,
        loss_avoided_usdt=Decimal("120"),
        profit_missed_usdt=Decimal("35"),
        drawdown_without_dge_pct=Decimal("0.12"),
        drawdown_with_dge_pct=Decimal("0.07"),
        counterfactual_expectancy_delta_usdt=Decimal("8.5"),
        computed_at=NOW,
    )

    surface = VirtualMarketRuntime.build_research_evidence_surface(
        session_id="snapshot:dge:1",
        portfolio_id="virtual:spot:dge:1",
        generation=1,
        configured_start_at=NOW - timedelta(days=400),
        feature_warmup_start=NOW - timedelta(days=430),
        last_replayed_at=NOW,
        market="SPOT",
        timeframe="1h",
        portfolio_performance=performance,
        attribution_ledger=ledger,
        walk_forward_report=walk_forward_report,
        robustness_report=robustness,
        dge_metrics=dge_metrics,
        replay_state_hash="hash-dge-1",
        observed_at=NOW,
    )

    snapshot: Any = surface.performance_snapshot
    assert snapshot.decision_outcome.counterfactual_return_usdt == Decimal("8.5")
    assert len(snapshot.counterfactuals) == 1
    assert snapshot.counterfactuals[0].counterfactual_id == "cf-no-dge:snapshot:dge:1"
    assert snapshot.counterfactuals[0].hypothetical_economic_outcome_usdt == Decimal(
        "8.5"
    )
    assert len(snapshot.blocker_effectiveness) == 1
    assert snapshot.blocker_effectiveness[0].outcome_class.value == "PROTECTIVE_BLOCK"
    assert snapshot.blocker_effectiveness[0].avoided_loss_usdt == Decimal("120")
    assert len(snapshot.decision_effectiveness) == 1
    assert (
        snapshot.decision_effectiveness[0].effectiveness_class.value
        == "BLOCKED_AVOIDED_LOSS"
    )
    dge_metric = next(
        metric
        for metric in snapshot.telemetry_snapshot.metrics
        if metric.metric_id == "virtual.dge_net_protection_value_usdt"
    )
    assert dge_metric.value == Decimal("85")


def test_virtual_market_runtime_surfaces_outcome_attributions() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:attr:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-attrib-5",
            candidate_id="candidate-attrib-5",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert losing is not None
    assert winning is not None
    ledger = VirtualMarketRuntime.build_trade_attribution_ledger((losing, winning))
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=(
            equity_point(0, "1000"),
            equity_point(1, "1015"),
            equity_point(2, "1025"),
            equity_point(3, "1040"),
        ),
    )
    walk_forward_report: Any = SimpleNamespace(
        report_id="wf:attr:1",
        blockers=(),
        folds=(),
    )
    robustness = BacktestRobustnessReport(
        stress_results=(
            StressResult(
                scenario=StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
                net_return=0.04,
                profit_factor=1.4,
                expectancy_usdt=4.0,
                max_drawdown=0.05,
                trade_count=2,
                delta_net_return=0.0,
                delta_profit_factor=0.0,
                delta_expectancy_usdt=0.0,
                delta_max_drawdown=0.0,
                delta_trade_count=0,
                spread_cost_usdt=0.5,
                funding_cost_usdt=0.0,
                funding_supported=False,
            ),
        ),
        bootstrap=BootstrapAssessment(
            simulations=1000,
            seed=42,
            probability_of_loss=0.20,
            median_net_return=0.03,
            p05_net_return=-0.01,
            p95_max_drawdown=0.10,
        ),
        blockers=(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=6,
        intervention_count=3,
        protective_block_count=2,
        false_block_count=1,
        loss_avoided_usdt=Decimal("120"),
        profit_missed_usdt=Decimal("35"),
        drawdown_without_dge_pct=Decimal("0.12"),
        drawdown_with_dge_pct=Decimal("0.07"),
        counterfactual_expectancy_delta_usdt=Decimal("8.5"),
        computed_at=NOW,
    )

    surface = VirtualMarketRuntime.build_research_evidence_surface(
        session_id="snapshot:attr:1",
        portfolio_id="virtual:spot:attr:1",
        generation=1,
        configured_start_at=NOW - timedelta(days=400),
        feature_warmup_start=NOW - timedelta(days=430),
        last_replayed_at=NOW,
        market="SPOT",
        timeframe="1h",
        portfolio_performance=performance,
        attribution_ledger=ledger,
        walk_forward_report=walk_forward_report,
        robustness_report=robustness,
        dge_metrics=dge_metrics,
        replay_state_hash="hash-attr-1",
        observed_at=NOW,
    )

    attributions = surface.performance_snapshot.attributions
    assert len(attributions) == 2
    execution_attribution = next(
        item
        for item in attributions
        if item.attribution_id == "attribution:execution-quality:snapshot:attr:1"
    )
    governance_attribution = next(
        item
        for item in attributions
        if item.attribution_id == "attribution:governance:snapshot:attr:1"
    )
    assert execution_attribution.has_economic_evidence is True
    assert execution_attribution.fee_effect_usdt == Decimal("-0.81979000")
    assert execution_attribution.slippage_effect_usdt == Decimal("-0.6")
    assert execution_attribution.funding_effect_usdt == Decimal("0")
    assert governance_attribution.governance_effect_usdt == Decimal("85")
    assert governance_attribution.decision_effect_usdt == Decimal("8.5")
    assert governance_attribution.avoided_loss_usdt == Decimal("120")
    assert governance_attribution.foregone_profit_usdt == Decimal("35")


def test_virtual_market_runtime_builds_measurable_no_trade_false_block_surface() -> (
    None
):
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:no-trade:false:1",
        decision_id="dge:no-trade:false:1",
        candidate_id="candidate:no-trade:false:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        strategy_id="breakout",
        strategy_version="2026.08",
        regime="TREND",
        timeframe="1h",
        dge_decision="BLOCKED",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:no-trade:false:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-no-trade-false-1",
            candidate_id="candidate:no-trade:false:1",
            entry_reason=("BREAKOUT_ENTRY",),
        ),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:no-trade:false:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert counterfactual_trade is not None
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=1,
        intervention_count=1,
        protective_block_count=0,
        false_block_count=1,
        loss_avoided_usdt=Decimal("0"),
        profit_missed_usdt=Decimal("17.78021000"),
        drawdown_without_dge_pct=Decimal("0.12"),
        drawdown_with_dge_pct=Decimal("0.12"),
        counterfactual_expectancy_delta_usdt=Decimal("17.78021000"),
        computed_at=NOW,
    )

    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:no-trade:false:1",
        request=request,
        blockers=("DGE_PROTECTIVE_BLOCK",),
        observed_at=NOW,
        replay_state_hash="hash-no-trade-false-1",
        dge_metrics=dge_metrics,
        counterfactual_trade=counterfactual_trade,
    )

    assert isinstance(surface, VirtualNoTradeEvidenceSurface)
    record = surface.missed_opportunity_ledger.records[0]
    assert record.counterfactual_result.value == "BAD_BLOCK"
    assert record.forward_net_pnl == counterfactual_trade.net_pnl_usdt
    assert surface.performance_snapshot.decision_outcome.measurable_no_trade is True
    assert (
        surface.performance_snapshot.blocker_effectiveness[0].outcome_class.value
        == "FALSE_BLOCK"
    )
    assert (
        surface.performance_snapshot.decision_effectiveness[0].effectiveness_class.value
        == "REJECTED_WOULD_PROFIT"
    )
    assert (
        surface.performance_snapshot.attributions[0].foregone_profit_usdt
        == counterfactual_trade.net_pnl_usdt
    )
    assert len(surface.improvement_candidates) == 1


def test_virtual_market_runtime_builds_measurable_no_trade_protective_block_surface() -> (
    None
):
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:no-trade:good:1",
        decision_id="dge:no-trade:good:1",
        candidate_id="candidate:no-trade:good:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        strategy_id="breakout",
        strategy_version="2026.08",
        regime="TREND",
        timeframe="1h",
        dge_decision="BLOCKED",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:no-trade:good:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-no-trade-good-1",
            candidate_id="candidate:no-trade:good:1",
            entry_reason=("BREAKOUT_ENTRY",),
        ),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:no-trade:good:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    assert counterfactual_trade is not None
    dge_metrics = DgeEffectivenessMetrics(
        sample_size=1,
        intervention_count=1,
        protective_block_count=1,
        false_block_count=0,
        loss_avoided_usdt=abs(counterfactual_trade.net_pnl_usdt),
        profit_missed_usdt=Decimal("0"),
        drawdown_without_dge_pct=Decimal("0.12"),
        drawdown_with_dge_pct=Decimal("0.10"),
        counterfactual_expectancy_delta_usdt=counterfactual_trade.net_pnl_usdt,
        computed_at=NOW,
    )

    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:no-trade:good:1",
        request=request,
        blockers=("RISK_VETO",),
        observed_at=NOW,
        replay_state_hash="hash-no-trade-good-1",
        dge_metrics=dge_metrics,
        counterfactual_trade=counterfactual_trade,
    )

    record = surface.missed_opportunity_ledger.records[0]
    assert record.counterfactual_result.value == "GOOD_BLOCK"
    assert (
        surface.performance_snapshot.blocker_effectiveness[0].outcome_class.value
        == "PROTECTIVE_BLOCK"
    )
    assert (
        surface.performance_snapshot.decision_effectiveness[0].effectiveness_class.value
        == "REJECTED_WOULD_LOSE"
    )
    assert surface.performance_snapshot.attributions[0].avoided_loss_usdt == abs(
        counterfactual_trade.net_pnl_usdt
    )
    opportunity_cost_type = surface.performance_snapshot.attributions[
        0
    ].opportunity_cost_type
    assert opportunity_cost_type is not None
    assert opportunity_cost_type.value == "RISK_VETO"
    assert surface.improvement_candidates == ()


def test_virtual_market_runtime_adapts_research_surface_for_consumers() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:adapter:research:1",
        market="SPOT",
        cash_usdt=Decimal("800"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("2"),
        inventory_cost_basis_usdt=Decimal("200"),
        open_position_count=1,
    )
    losing = runtime.process_position(
        position=attributed_open_virtual_position(),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    ).closed_trade
    winning = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-adapter-research-1",
            candidate_id="candidate-adapter-research-1",
            regime="RANGE",
            entry_reason=("RANGE_REVERSION",),
        ),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert losing is not None
    assert winning is not None
    walk_forward_report: Any = SimpleNamespace(
        report_id="wf:adapter:research:1", blockers=(), folds=()
    )
    surface = VirtualMarketRuntime.build_research_evidence_surface(
        session_id="snapshot:adapter:research:1",
        portfolio_id="virtual:spot:adapter:research:1",
        generation=1,
        configured_start_at=NOW - timedelta(days=400),
        feature_warmup_start=NOW - timedelta(days=430),
        last_replayed_at=NOW,
        market="SPOT",
        timeframe="1h",
        portfolio_performance=VirtualMarketRuntime.calculate_portfolio_performance(
            market="SPOT",
            equity_curve=(
                equity_point(0, "1000"),
                equity_point(1, "1015"),
                equity_point(2, "1025"),
                equity_point(3, "1040"),
            ),
        ),
        attribution_ledger=VirtualMarketRuntime.build_trade_attribution_ledger(
            (losing, winning)
        ),
        walk_forward_report=walk_forward_report,
        robustness_report=BacktestRobustnessReport(
            stress_results=(
                StressResult(
                    scenario=StressScenario(
                        "BASE", Decimal("0.001"), Decimal("0.0005")
                    ),
                    net_return=0.04,
                    profit_factor=1.4,
                    expectancy_usdt=4.0,
                    max_drawdown=0.05,
                    trade_count=2,
                    delta_net_return=0.0,
                    delta_profit_factor=0.0,
                    delta_expectancy_usdt=0.0,
                    delta_max_drawdown=0.0,
                    delta_trade_count=0,
                    spread_cost_usdt=0.5,
                    funding_cost_usdt=0.0,
                    funding_supported=False,
                ),
            ),
            bootstrap=BootstrapAssessment(
                simulations=1000,
                seed=42,
                probability_of_loss=0.20,
                median_net_return=0.03,
                p05_net_return=-0.01,
                p95_max_drawdown=0.10,
            ),
            blockers=(),
            promotion_status=ValidationStatus.RESEARCH_ONLY,
        ),
        dge_metrics=DgeEffectivenessMetrics(
            sample_size=1,
            intervention_count=0,
            protective_block_count=0,
            false_block_count=0,
            loss_avoided_usdt=Decimal("0"),
            profit_missed_usdt=Decimal("0"),
            drawdown_without_dge_pct=Decimal("0.04"),
            drawdown_with_dge_pct=Decimal("0.04"),
            counterfactual_expectancy_delta_usdt=Decimal("0"),
            computed_at=NOW,
        ),
        replay_state_hash="hash-adapter-research-1",
        observed_at=NOW,
    )

    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    assert isinstance(adapter, VirtualEvidenceSurfaceAdapter)
    assert adapter.surface_kind == "RESEARCH"
    assert (
        adapter.telemetry_snapshot.telemetry_id
        == surface.performance_snapshot.snapshot_id
    )
    assert adapter.telemetry_snapshot.blockers == surface.blockers
    assert adapter.acceptance_results == surface.performance_snapshot.acceptance_results
    assert (
        adapter.primary_acceptance.result_id
        == surface.performance_snapshot.acceptance_results[0].result_id
    )


def test_virtual_market_runtime_adapts_no_trade_surface_for_consumers() -> None:
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:adapter:no-trade:1",
        decision_id="dge:adapter:no-trade:1",
        candidate_id="candidate:adapter:no-trade:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        strategy_id="breakout",
        strategy_version="2026.08",
        regime="TREND",
        timeframe="1h",
        dge_decision="BLOCKED",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:adapter:no-trade:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-adapter-no-trade-1",
            candidate_id="candidate:adapter:no-trade:1",
            entry_reason=("BREAKOUT_ENTRY",),
        ),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:adapter:no-trade:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert counterfactual_trade is not None
    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:adapter:no-trade:1",
        request=request,
        blockers=("DGE_PROTECTIVE_BLOCK",),
        observed_at=NOW,
        replay_state_hash="hash-adapter-no-trade-1",
        dge_metrics=DgeEffectivenessMetrics(
            sample_size=1,
            intervention_count=1,
            protective_block_count=0,
            false_block_count=1,
            loss_avoided_usdt=Decimal("0"),
            profit_missed_usdt=counterfactual_trade.net_pnl_usdt,
            drawdown_without_dge_pct=Decimal("0.12"),
            drawdown_with_dge_pct=Decimal("0.12"),
            counterfactual_expectancy_delta_usdt=counterfactual_trade.net_pnl_usdt,
            computed_at=NOW,
        ),
        counterfactual_trade=counterfactual_trade,
    )

    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    assert isinstance(adapter, VirtualEvidenceSurfaceAdapter)
    assert adapter.surface_kind == "NO_TRADE"
    assert adapter.telemetry_snapshot.blockers == ("DGE_PROTECTIVE_BLOCK",)
    assert adapter.blockers == ("DGE_PROTECTIVE_BLOCK",)
    assert len(adapter.acceptance_results) == 1
    assert (
        adapter.primary_acceptance.result_id
        == "acceptance:snapshot:adapter:no-trade:1:no-trade"
    )
    assert adapter.primary_acceptance.gate_eligible is False
    assert (
        adapter.primary_acceptance.gate_results["NO_TRADE_MEASUREMENT"].value == "PASS"
    )


def test_virtual_market_runtime_rejects_inconsistent_evidence_surface_adapter_contract() -> (
    None
):
    surface = research_surface_for_staging("snapshot:adapter:contract:1")
    telemetry_snapshot = surface.performance_snapshot.telemetry_snapshot
    assert telemetry_snapshot is not None
    mismatched_telemetry = replace(
        telemetry_snapshot,
        blockers=("MISMATCHED_BLOCKER",),
    )

    with pytest.raises(ValueError, match="blockers must match telemetry"):
        VirtualEvidenceSurfaceAdapter(
            surface_kind="RESEARCH",
            market=surface.market_performance.market.value,
            performance_snapshot=surface.performance_snapshot,
            telemetry_snapshot=mismatched_telemetry,
            acceptance_results=surface.performance_snapshot.acceptance_results,
            improvement_candidates=surface.improvement_candidates,
            blockers=surface.blockers,
        )

    with pytest.raises(ValueError, match="requires acceptance results"):
        VirtualEvidenceSurfaceAdapter(
            surface_kind="RESEARCH",
            market=surface.market_performance.market.value,
            performance_snapshot=surface.performance_snapshot,
            telemetry_snapshot=telemetry_snapshot,
            acceptance_results=(),
            improvement_candidates=surface.improvement_candidates,
            blockers=surface.blockers,
        )


def test_virtual_evidence_surface_adapter_rejects_unsupported_market() -> None:
    surface = research_surface_for_staging("snapshot:adapter:market:1")
    telemetry_snapshot = surface.performance_snapshot.telemetry_snapshot
    assert telemetry_snapshot is not None

    with pytest.raises(
        ValueError,
        match="virtual evidence adapter market must be SPOT or USD_M_FUTURES",
    ):
        VirtualEvidenceSurfaceAdapter(
            surface_kind="RESEARCH",
            market="OPTIONS",
            performance_snapshot=surface.performance_snapshot,
            telemetry_snapshot=telemetry_snapshot,
            acceptance_results=surface.performance_snapshot.acceptance_results,
            improvement_candidates=surface.improvement_candidates,
            blockers=surface.blockers,
        )


def test_virtual_market_runtime_builds_publication_payload_and_markdown() -> None:
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:publish:no-trade:1",
        decision_id="dge:publish:no-trade:1",
        candidate_id="candidate:publish:no-trade:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        strategy_id="breakout",
        strategy_version="2026.08",
        regime="TREND",
        timeframe="1h",
        dge_decision="BLOCKED",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:publish:no-trade:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-publish-no-trade-1",
            candidate_id="candidate:publish:no-trade:1",
            entry_reason=("BREAKOUT_ENTRY",),
        ),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:publish:no-trade:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert counterfactual_trade is not None
    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:publish:no-trade:1",
        request=request,
        blockers=("DGE_PROTECTIVE_BLOCK",),
        observed_at=NOW,
        replay_state_hash="hash-publish-no-trade-1",
        dge_metrics=DgeEffectivenessMetrics(
            sample_size=1,
            intervention_count=1,
            protective_block_count=0,
            false_block_count=1,
            loss_avoided_usdt=Decimal("0"),
            profit_missed_usdt=counterfactual_trade.net_pnl_usdt,
            drawdown_without_dge_pct=Decimal("0.12"),
            drawdown_with_dge_pct=Decimal("0.12"),
            counterfactual_expectancy_delta_usdt=counterfactual_trade.net_pnl_usdt,
            computed_at=NOW,
        ),
        counterfactual_trade=counterfactual_trade,
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    payload: Any = VirtualMarketRuntime.evidence_surface_payload(adapter)
    markdown = VirtualMarketRuntime.render_evidence_surface_markdown(adapter)

    assert payload["surface_kind"] == "NO_TRADE"
    assert payload["market"] == "SPOT"
    assert payload["snapshot_id"] == "snapshot:publish:no-trade:1"
    assert payload["execution_allowed"] is False
    assert payload["telemetry_blockers"] == ("DGE_PROTECTIVE_BLOCK",)
    assert payload["acceptance_results"][0]["blockers"] == ("DGE_PROTECTIVE_BLOCK",)
    assert "Virtual Evidence Surface NO_TRADE" in markdown
    assert "Market: `SPOT`" in markdown
    assert "LIVE_ORDER_BLOCKED" in markdown
    assert "snapshot:publish:no-trade:1" in markdown


def test_virtual_market_runtime_publishes_system_acceptance_report(
    tmp_path: Path,
) -> None:
    spot = MarketAcceptanceResult(
        market=VirtualMarket.SPOT,
        status=AcceptanceStatus.FAIL,
        blockers=("NET_RETURN_NOT_POSITIVE",),
        evidence_refs=("spot-session", "spot-hash"),
        policy_id="virtual-market-research-acceptance-v1",
    )
    futures = MarketAcceptanceResult(
        market=VirtualMarket.USD_M_FUTURES,
        status=AcceptanceStatus.PASS,
        blockers=(),
        evidence_refs=("futures-session", "futures-hash"),
        policy_id="virtual-market-research-acceptance-v1",
    )
    system = SystemResearchAcceptance.derive(spot, futures)

    paths = VirtualMarketRuntime.publish_system_acceptance_report(
        system,
        root=tmp_path,
        stamp="20260826-virtual-system-acceptance",
    )

    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    markdown = paths.markdown_path.read_text(encoding="utf-8")

    assert payload["surface_kind"] == "SYSTEM_ACCEPTANCE"
    assert payload["spot"]["market"] == "SPOT"
    assert payload["futures"]["market"] == "USD_M_FUTURES"
    assert payload["spot"]["status"] == "FAIL"
    assert payload["futures"]["status"] == "PASS"
    assert "combined_pnl" not in json.dumps(payload, sort_keys=True)
    assert "Spot Acceptance" in markdown
    assert "USD_M Futures Acceptance" in markdown
    assert "SYSTEM_FAIL" in markdown
    assert "RESEARCH_ONLY" in markdown
    assert "LIVE_ORDER_BLOCKED" in markdown


def test_virtual_market_runtime_publishes_evidence_surface_files(
    tmp_path: Path,
) -> None:
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:publish:files:1",
        decision_id="dge:publish:files:1",
        candidate_id="candidate:publish:files:1",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"), Decimal("120")),
        strategy_id="breakout",
        strategy_version="2026.08",
        regime="TREND",
        timeframe="1h",
        dge_decision="BLOCKED",
        risk_policy_version="risk-v2",
        validation_version="validation-v5",
        entry_reason=("BREAKOUT_ENTRY",),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:publish:files:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-publish-files-1",
            candidate_id="candidate:publish:files:1",
            entry_reason=("BREAKOUT_ENTRY",),
        ),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:publish:files:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert counterfactual_trade is not None
    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:publish:files:1",
        request=request,
        blockers=("DGE_PROTECTIVE_BLOCK",),
        observed_at=NOW,
        replay_state_hash="hash-publish-files-1",
        dge_metrics=DgeEffectivenessMetrics(
            sample_size=1,
            intervention_count=1,
            protective_block_count=0,
            false_block_count=1,
            loss_avoided_usdt=Decimal("0"),
            profit_missed_usdt=counterfactual_trade.net_pnl_usdt,
            drawdown_without_dge_pct=Decimal("0.12"),
            drawdown_with_dge_pct=Decimal("0.12"),
            counterfactual_expectancy_delta_usdt=counterfactual_trade.net_pnl_usdt,
            computed_at=NOW,
        ),
        counterfactual_trade=counterfactual_trade,
    )
    surface = replace(
        surface,
        performance_snapshot=replace(
            surface.performance_snapshot,
            gpu_telemetry_assessment=_gpu_assessment(),
        ),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_evidence_surface(
        adapter,
        root=tmp_path,
        stamp="20260824T120000Z",
    )

    assert paths.report_dir == tmp_path / "runtime" / "reports" / "virtual_evidence"
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert (paths.artifact_dir / "virtual_no_trade_spot_evidence_latest.json").exists()
    assert (paths.report_dir / "virtual_no_trade_spot_evidence_latest.md").exists()
    payload: Any = json.loads(paths.json_path.read_text(encoding="utf-8"))
    assert (
        payload["telemetry_metric_summary"]["virtual.no_trade_counterfactual_pnl_usdt"][
            "unit"
        ]
        == "USDT"
    )
    assert payload["telemetry_blockers"] == ["DGE_PROTECTIVE_BLOCK"]
    gpu_assessment = cast(dict[str, Any], payload["gpu_telemetry_assessment"])
    assert gpu_assessment["source_label"] == "nvidia-smi"
    assert gpu_assessment["healthy"] is True
    assert payload["telemetry_metric_summary"]["virtual.no_trade_counterfactual_r"][
        "value"
    ]
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "snapshot:publish:files:1" in markdown
    assert "## GPU Governance" in markdown


def _gpu_assessment() -> GpuTelemetryAssessment:
    return GpuTelemetryAssessment(
        observed_at=NOW,
        source_label="nvidia-smi",
        cuda_available=True,
        device_name="NVIDIA GeForce RTX 4090",
        driver_version="555.85",
        total_vram_bytes=24_064_000_000,
        free_vram_bytes=18_048_000_000,
        gpu_utilization_pct=21,
        active_gpu_processes=1,
        headroom_percent=30,
        healthy=True,
        blockers=(),
    )


def test_virtual_market_runtime_publishes_loss_streak_halt_review(
    tmp_path: Path,
) -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:halt:publish:1",
            decision_id="dge:halt:publish:1",
            candidate_id="candidate:halt:publish:1",
            symbol="HOTUSDT",
            market="SPOT",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            strategy_id="breakout",
            strategy_version="2026.08",
            regime="TREND",
            portfolio_governor=VirtualPortfolioRiskGovernor(
                maximum_consecutive_losses=3,
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:spot:halt:publish:1",
                market="SPOT",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
                consecutive_losses=3,
            ),
        )
    )

    assert decision.halt_review is not None

    paths = VirtualMarketRuntime.publish_loss_streak_halt_review(
        decision.halt_review,
        root=tmp_path,
        stamp="20260825T090000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_loss_streak_halt_review"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    registry_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
        / "review_registry_latest.json"
    )
    registry_history_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
        / "review_registry.jsonl"
    )
    assert registry_path.exists()
    assert registry_history_path.exists()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    history_entries = [
        json.loads(line)
        for line in registry_history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert registry["review_ref"] == decision.halt_review.review_id
    assert registry["artifact_path"].endswith(".json")
    assert history_entries[-1]["review_ref"] == decision.halt_review.review_id
    payload: Any = json.loads(paths.json_path.read_text(encoding="utf-8"))
    assert payload["root_cause_tags"] == [
        "ENTRY_GATING_REVIEW",
        "REGIME_FIT_REVIEW",
        "EXIT_PROTECTION_REVIEW",
    ]
    assert (
        "under-calibrated" in payload["next_bounded_experiment"]
        or "Freeze the halted scope" in payload["next_bounded_experiment"]
    )
    assert "root cause" in paths.markdown_path.read_text(encoding="utf-8").lower()
    assert "Virtual Loss Streak Halt Review SPOT" in paths.markdown_path.read_text(
        encoding="utf-8"
    )


def test_virtual_loss_streak_halt_review_rejects_unsupported_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual halt review market must be SPOT or USD_M_FUTURES",
    ):
        research_virtual_runtime.VirtualLossStreakHaltReview(
            review_id="virtual-halt-review:1",
            snapshot_id="snapshot:halt:1",
            decision_id="decision:halt:1",
            portfolio_id="portfolio:halt:1",
            halt_scope="LOSS_STREAK",
            status=research_virtual_runtime.VirtualAutonomyHaltStatus.ACTIVE,
            trigger_blocker="VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
            market="OPTIONS",
            symbol="HOTUSDT",
            strategy_id="breakout",
            strategy_version="2026.08",
            regime="TREND",
            consecutive_losses=2,
            maximum_consecutive_losses=2,
            findings=("LOSS_STREAK_TRIPPED",),
            root_cause_tags=("ENTRY_GATING_REVIEW",),
            root_cause_summary="Loss streak exceeded the governed threshold.",
            next_bounded_experiment="Freeze the halted scope and review the entry gate.",
            reset_criteria=("RESET_AFTER_REVIEW",),
        )


def test_virtual_market_runtime_compacts_halt_review_registry_history(
    tmp_path: Path,
) -> None:
    registry_history_path = (
        tmp_path
        / "reports"
        / "virtual_loss_streak_halt_review"
        / "review_registry.jsonl"
    )
    registry_history_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        json.dumps(
            {
                "review_ref": f"virtual-loss-streak-halt:test:{index}",
                "artifact_path": f"runtime/artifacts/user_reports/virtual_loss_streak_halt_review/{index}.json",
            },
            sort_keys=True,
        )
        for index in range(5)
    ]
    registry_history_path.write_text("\n".join(entries) + "\n", encoding="utf-8")

    VirtualMarketRuntime._compact_halt_review_registry_history(
        registry_history_path,
        keep_last=2,
    )

    compacted = registry_history_path.read_text(encoding="utf-8").splitlines()
    assert len(compacted) == 2
    assert "virtual-loss-streak-halt:test:3" in compacted[0]
    assert "virtual-loss-streak-halt:test:4" in compacted[1]


def test_virtual_market_runtime_compaction_preserves_latest_entry_per_review_ref(
    tmp_path: Path,
) -> None:
    registry_history_path = (
        tmp_path
        / "reports"
        / "virtual_loss_streak_halt_review"
        / "review_registry.jsonl"
    )
    registry_history_path.parent.mkdir(parents=True, exist_ok=True)
    entries = (
        {
            "review_ref": "virtual-loss-streak-halt:test:A",
            "artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/a-1.json",
        },
        {
            "review_ref": "virtual-loss-streak-halt:test:B",
            "artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/b-1.json",
        },
        {
            "review_ref": "virtual-loss-streak-halt:test:A",
            "artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/a-2.json",
        },
    )
    registry_history_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in entries) + "\n",
        encoding="utf-8",
    )

    VirtualMarketRuntime._compact_halt_review_registry_history(
        registry_history_path,
        keep_last=2,
    )

    compacted = [
        json.loads(line)
        for line in registry_history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(compacted) == 2
    assert compacted[0]["review_ref"] == "virtual-loss-streak-halt:test:B"
    assert compacted[1]["review_ref"] == "virtual-loss-streak-halt:test:A"
    assert compacted[1]["artifact_path"].endswith("a-2.json")


def test_virtual_market_runtime_stages_improvement_candidates_from_virtual_evidence() -> (
    None
):
    surface = research_surface_for_staging()
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    staged = VirtualMarketRuntime.stage_improvement_candidates(adapter)
    payload: Any = VirtualMarketRuntime.staged_improvement_payload(adapter)
    markdown = VirtualMarketRuntime.render_staged_improvement_markdown(adapter)

    assert len(staged) == 1
    assert isinstance(staged[0], VirtualStagedImprovementCandidate)
    assert staged[0].promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert staged[0].candidate.promotion_status == "RESEARCH_ONLY"
    assert staged[0].execution_allowed is False
    assert (
        staged[0]
        .assurance_artifact_refs[0]
        .endswith("virtual_research_improvement_queue_assurance_latest.json")
    )
    assert payload["staged_candidate_count"] == 1
    assert payload["staged_candidates"][0]["assurance_artifact_refs"][0].endswith(
        "virtual_research_improvement_queue_assurance_latest.json"
    )
    assert "Virtual Improvement Candidate Staging RESEARCH" in markdown
    assert "STAGED_CANDIDATE" in markdown


def test_virtual_market_runtime_keeps_insufficient_improvement_evidence_research_only() -> (
    None
):
    surface = research_surface_for_staging("snapshot:stage:research:insufficient:1")
    degraded_surface = replace(
        surface,
        improvement_candidates=(
            replace(
                surface.improvement_candidates[0],
                evidence_quality=EvidenceQuality.INSUFFICIENT,
            ),
        ),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(degraded_surface)

    staged = VirtualMarketRuntime.stage_improvement_candidates(adapter)

    assert len(staged) == 1
    assert staged[0].promotion_status is ValidationStatus.RESEARCH_ONLY
    assert staged[0].blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)
    assert staged[0].live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_virtual_market_runtime_publishes_staged_improvement_candidates(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:stage:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_staged_improvement_candidates(
        adapter,
        root=tmp_path,
        stamp="20260824T130000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_candidates"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "STAGED_CANDIDATE" in paths.markdown_path.read_text(encoding="utf-8")


def test_virtual_market_runtime_blocks_improvement_publish_without_candidates() -> None:
    surface = research_surface_for_staging("snapshot:stage:blocked:1")
    empty_surface = replace(surface, improvement_candidates=())
    adapter = VirtualMarketRuntime.adapt_evidence_surface(empty_surface)

    with pytest.raises(ValueError, match="requires improvement candidates"):
        VirtualMarketRuntime.stage_improvement_candidates(adapter)


def test_virtual_market_runtime_blocks_improvement_publish_without_telemetry() -> None:
    adapter: Any = SimpleNamespace(
        surface_kind="RESEARCH",
        snapshot_id="snapshot:stage:missing-telemetry:1",
        telemetry_snapshot=None,
        performance_snapshot=SimpleNamespace(lineage=SimpleNamespace(complete=True)),
        improvement_candidates=(SimpleNamespace(candidate_id="candidate:1"),),
    )

    with pytest.raises(ValueError, match="requires canonical telemetry"):
        VirtualMarketRuntime.stage_improvement_candidates(adapter)


def test_virtual_market_runtime_blocks_improvement_publish_with_incomplete_lineage() -> (
    None
):
    adapter: Any = SimpleNamespace(
        surface_kind="RESEARCH",
        snapshot_id="snapshot:stage:incomplete-lineage:1",
        telemetry_snapshot=SimpleNamespace(
            telemetry_id="snapshot:stage:incomplete-lineage:1"
        ),
        performance_snapshot=SimpleNamespace(lineage=SimpleNamespace(complete=False)),
        improvement_candidates=(SimpleNamespace(candidate_id="candidate:1"),),
    )

    with pytest.raises(ValueError, match="requires complete lineage"):
        VirtualMarketRuntime.stage_improvement_candidates(adapter)


def test_virtual_market_runtime_builds_ready_improvement_research_queue() -> None:
    surface = research_surface_for_staging("snapshot:queue:ready:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
    markdown = VirtualMarketRuntime.render_improvement_research_queue_markdown(adapter)
    payload: Any = queue.to_payload()

    assert isinstance(queue, VirtualImprovementResearchQueue)
    assert queue.queue_id == "virtual-improvement-queue:snapshot:queue:ready:1"
    assert queue.triage_reason == "SAMPLE_BUILD_PRIORITY"
    assert queue.status == "READY"
    assert queue.assurance_artifact_refs[0].endswith(
        "virtual_research_improvement_queue_assurance_latest.json"
    )
    assert len(queue.items) == 1
    assert queue.items[0].triage_reason == "SAMPLE_BUILD_PRIORITY"
    assert queue.items[0].priority == "P0"
    assert queue.items[0].status == "QUEUED_RESEARCH_ONLY"
    assert (
        queue.items[0]
        .assurance_artifact_refs[0]
        .endswith("virtual_research_improvement_queue_assurance_latest.json")
    )
    assert (
        queue.items[0]
        .required_artifacts[0]
        .endswith("virtual_research_evidence_latest.json")
    )
    assert payload["assurance_artifact_refs"][0].endswith(
        "virtual_research_improvement_queue_assurance_latest.json"
    )
    assert payload["triage_reason"] == "SAMPLE_BUILD_PRIORITY"
    handoff = payload["items"][0]["handoff"]
    assert handoff["schema_version"] == "VirtualImprovementResearchHandoff/v1"
    assert handoff["task_type"] == "VIRTUAL_IMPROVEMENT_REVIEW"
    assert handoff["triage_reason"] == "SAMPLE_BUILD_PRIORITY"
    assert handoff["context_refs"][0].startswith("virtual-improvement-stage:")
    assert "VirtualImprovementResearchQueue" in handoff["governance_refs"]
    assert (
        "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
        "virtual_research_improvement_queue_assurance_latest.json"
    ) in handoff["evidence_refs"]
    assert handoff["required_output_fields"] == (
        "review_outcome",
        "recommended_experiment",
        "evidence_gap_assessment",
    )
    assert "Virtual Improvement Research Queue RESEARCH" in markdown
    assert "SAMPLE_BUILD_PRIORITY" in markdown
    assert "READY" in markdown


def test_virtual_market_runtime_builds_blocked_improvement_research_queue() -> None:
    surface = research_surface_for_staging("snapshot:queue:blocked:1")
    degraded_surface = replace(
        surface,
        improvement_candidates=(
            replace(
                surface.improvement_candidates[0],
                evidence_quality=EvidenceQuality.INSUFFICIENT,
            ),
        ),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(degraded_surface)

    queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)

    assert queue.status == "QUEUED_WITH_BLOCKERS"
    assert queue.triage_reason == "SAMPLE_BUILD_PRIORITY"
    assert queue.blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)
    assert queue.items[0].priority == "P1"
    assert queue.items[0].triage_reason == "SAMPLE_BUILD_PRIORITY"
    assert queue.items[0].blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)


def test_virtual_market_runtime_orders_improvement_research_queue_by_evidence_strength() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:ordered:1")
    stronger = replace(
        surface.improvement_candidates[0],
        candidate_id="improvement:stronger",
        confidence=Decimal("0.90"),
        sample_size=8,
        opportunity_cost_delta_usdt=Decimal("14"),
    )
    weaker = replace(
        surface.improvement_candidates[0],
        candidate_id="improvement:weaker",
        confidence=Decimal("0.70"),
        sample_size=4,
        opportunity_cost_delta_usdt=Decimal("6"),
    )
    ordered_surface = replace(
        surface,
        improvement_candidates=(weaker, stronger),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(ordered_surface)

    queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)

    assert [item.candidate_id for item in queue.items] == [
        "improvement:stronger",
        "improvement:weaker",
    ]
    assert [item.priority for item in queue.items] == ["P0", "P0"]


def test_virtual_market_runtime_orders_staged_candidates_ahead_of_blocked_candidates() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:promotion-order:1")
    staged_candidate = replace(
        surface.improvement_candidates[0],
        candidate_id="improvement:staged",
        confidence=Decimal("0.60"),
        sample_size=2,
        opportunity_cost_delta_usdt=Decimal("3"),
    )
    blocked_candidate = replace(
        surface.improvement_candidates[0],
        candidate_id="improvement:blocked",
        evidence_quality=EvidenceQuality.INSUFFICIENT,
        confidence=Decimal("0.95"),
        sample_size=12,
        opportunity_cost_delta_usdt=Decimal("20"),
    )
    mixed_surface = replace(
        surface,
        improvement_candidates=(blocked_candidate, staged_candidate),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(mixed_surface)

    queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)

    assert [item.candidate_id for item in queue.items] == [
        "improvement:staged",
        "improvement:blocked",
    ]
    assert [item.priority for item in queue.items] == ["P0", "P1"]


def test_virtual_market_runtime_publishes_improvement_research_queue(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_queue(
        adapter,
        root=tmp_path,
        stamp="20260824T140000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_queue"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert (
        "virtual-improvement-queue:snapshot:queue:publish:1"
        in paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_no_trade_queue_carries_counterfactual_triage_reason() -> (
    None
):
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:queue:no-trade:1",
        decision_id="dge:queue:no-trade:1",
        candidate_id="candidate:queue:no-trade:1",
        symbol="BTCUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:spot:queue:no-trade:1",
            market="SPOT",
            cash_usdt=Decimal("800"),
            equity_usdt=Decimal("1000"),
            inventory_quantity=Decimal("2"),
            inventory_cost_basis_usdt=Decimal("200"),
            open_position_count=1,
        ),
    )
    runtime = VirtualMarketRuntime()
    counterfactual_trade = runtime.process_position(
        position=replace(
            attributed_open_virtual_position(),
            position_id="virtual-position-queue-no-trade-1",
            candidate_id="candidate:queue:no-trade:1",
        ),
        portfolio=request.portfolio,
        candle=lifecycle_candle(1, "100", "121", "99", "118"),
    ).closed_trade
    assert counterfactual_trade is not None
    surface = VirtualMarketRuntime.build_no_trade_evidence_surface(
        session_id="snapshot:queue:no-trade:1",
        request=request,
        blockers=("DGE_PROTECTIVE_BLOCK",),
        observed_at=NOW,
        replay_state_hash="hash-queue-no-trade-1",
        dge_metrics=DgeEffectivenessMetrics(
            sample_size=1,
            intervention_count=1,
            protective_block_count=0,
            false_block_count=1,
            loss_avoided_usdt=Decimal("0"),
            profit_missed_usdt=counterfactual_trade.net_pnl_usdt,
            drawdown_without_dge_pct=Decimal("0.12"),
            drawdown_with_dge_pct=Decimal("0.12"),
            counterfactual_expectancy_delta_usdt=counterfactual_trade.net_pnl_usdt,
            computed_at=NOW,
        ),
        counterfactual_trade=counterfactual_trade,
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
    payload: Any = queue.to_payload()

    assert queue.triage_reason == "COUNTERFACTUAL_REVIEW_PRIORITY"
    assert queue.items[0].triage_reason == "COUNTERFACTUAL_REVIEW_PRIORITY"
    assert payload["triage_reason"] == "COUNTERFACTUAL_REVIEW_PRIORITY"
    assert payload["items"][0]["handoff"]["triage_reason"] == (
        "COUNTERFACTUAL_REVIEW_PRIORITY"
    )


def test_virtual_market_runtime_builds_ready_improvement_queue_assurance_bundle() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:assurance:ready:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    bundle = VirtualMarketRuntime.build_improvement_research_queue_assurance_bundle(
        adapter
    )
    payload: Any = bundle.to_payload()

    assert isinstance(bundle, TrustAssuranceBundle)
    assert bundle.provenance.final_action == "READY"
    assert bundle.policy_evaluations[0].result is TrustAssuranceResult.PASSED
    assert bundle.uncertainty.level is UncertaintyLevel.LOW
    assert bundle.semantic_contracts[0].subject == "VirtualImprovementResearchHandoff"
    assert payload["framework"] == "AI4BINANCE_TIAF_LITE"
    assert payload["provenance"]["final_action"] == "READY"


def test_virtual_market_runtime_builds_blocked_improvement_queue_assurance_bundle() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:assurance:blocked:1")
    degraded_surface = replace(
        surface,
        improvement_candidates=(
            replace(
                surface.improvement_candidates[0],
                evidence_quality=EvidenceQuality.INSUFFICIENT,
            ),
        ),
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(degraded_surface)

    bundle = VirtualMarketRuntime.build_improvement_research_queue_assurance_bundle(
        adapter
    )

    assert bundle.provenance.final_action == "QUEUED_WITH_BLOCKERS"
    assert bundle.policy_evaluations[0].result is TrustAssuranceResult.WARN
    assert bundle.policy_evaluations[0].blockers == (
        "IMPROVEMENT_EVIDENCE_INSUFFICIENT",
    )
    assert bundle.uncertainty.level is UncertaintyLevel.MEDIUM


def test_virtual_market_runtime_renders_improvement_queue_assurance_markdown() -> None:
    surface = research_surface_for_staging("snapshot:queue:assurance:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_research_queue_assurance_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Queue Assurance RESEARCH" in markdown
    assert "AI4BINANCE_TIAF_LITE" in markdown
    assert "ASSURANCE_READY_FOR_RESEARCH_REVIEW" in markdown
    assert "LIVE_ORDER_BLOCKED" in markdown


def test_virtual_market_runtime_publishes_improvement_queue_assurance(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:assurance:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_queue_assurance(
        adapter,
        root=tmp_path,
        stamp="20260824T150000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_queue_assurance"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "AI4BINANCE_TIAF_LITE" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Queue Assurance RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_review_results() -> None:
    surface = research_surface_for_staging("snapshot:queue:review-results:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    results = VirtualMarketRuntime.build_improvement_review_results(adapter)
    payload: Any = VirtualMarketRuntime.improvement_review_results_payload(adapter)

    assert len(results) == 1
    assert results[0].outcome.value == "EXPERIMENT_PROPOSAL"
    assert (
        results[0]
        .follow_up_artifact_refs[0]
        .endswith("research_virtual_improvement_review_latest.json")
    )
    assert payload["status"] == "READY_FOR_EXPERIMENT_PROPOSAL"
    assert payload["review_results"][0]["outcome"] == "EXPERIMENT_PROPOSAL"


def test_virtual_market_runtime_renders_improvement_review_results_markdown() -> None:
    surface = research_surface_for_staging("snapshot:queue:review-results:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_review_results_markdown(adapter)

    assert "Virtual Improvement Review Results RESEARCH" in markdown
    assert "EXPERIMENT_PROPOSAL" in markdown
    assert "READY_FOR_EXPERIMENT_PROPOSAL" in markdown


def test_virtual_market_runtime_publishes_improvement_review_results(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:review-results:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_review_results(
        adapter,
        root=tmp_path,
        stamp="20260825T090000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_reviews"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "EXPERIMENT_PROPOSAL" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Review Results RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_experiment_proposals() -> None:
    surface = research_surface_for_staging("snapshot:queue:experiments:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    proposals = VirtualMarketRuntime.build_improvement_experiment_proposals(adapter)
    payload: Any = VirtualMarketRuntime.improvement_experiment_proposals_payload(
        adapter
    )

    assert len(proposals) == 1
    assert proposals[0].priority == "P0"
    assert (
        proposals[0]
        .source_artifact_refs[0]
        .endswith("virtual_research_improvement_queue_assurance_latest.json")
    )
    assert payload["status"] == "READY_FOR_BOUNDED_EXPERIMENT"
    assert payload["proposals"][0]["priority"] == "P0"


def test_virtual_market_runtime_renders_improvement_experiment_proposals_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:experiments:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_experiment_proposals_markdown(
        adapter
    )

    assert "Virtual Improvement Experiment Proposals RESEARCH" in markdown
    assert "READY_FOR_BOUNDED_EXPERIMENT" in markdown
    assert "P0" in markdown


def test_virtual_market_runtime_publishes_improvement_experiment_proposals(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:experiments:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_experiment_proposals(
        adapter,
        root=tmp_path,
        stamp="20260825T100000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_experiments"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_FOR_BOUNDED_EXPERIMENT" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Experiment Proposals RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_experiment_tasks() -> None:
    surface = research_surface_for_staging("snapshot:queue:tasks:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    tasks = VirtualMarketRuntime.build_improvement_experiment_tasks(adapter)
    payload: Any = VirtualMarketRuntime.improvement_experiment_tasks_payload(adapter)

    assert len(tasks) == 1
    assert tasks[0].status.value == "READY_FOR_RESEARCH"
    assert (
        tasks[0]
        .source_artifact_refs[0]
        .endswith("virtual_research_improvement_queue_assurance_latest.json")
    )
    assert payload["status"] == "TASKS_READY_FOR_RESEARCH"
    assert payload["tasks"][0]["status"] == "READY_FOR_RESEARCH"


def test_virtual_market_runtime_renders_improvement_experiment_tasks_markdown() -> None:
    surface = research_surface_for_staging("snapshot:queue:tasks:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_experiment_tasks_markdown(
        adapter
    )

    assert "Virtual Improvement Experiment Tasks RESEARCH" in markdown
    assert "TASKS_READY_FOR_RESEARCH" in markdown
    assert "READY_FOR_RESEARCH" in markdown


def test_virtual_market_runtime_publishes_improvement_experiment_tasks(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:tasks:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_experiment_tasks(
        adapter,
        root=tmp_path,
        stamp="20260825T110000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_tasks"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "TASKS_READY_FOR_RESEARCH" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Experiment Tasks RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_experiment_task_queue() -> None:
    surface = research_surface_for_staging("snapshot:queue:task-queue:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    queue = VirtualMarketRuntime.build_improvement_experiment_task_queue(adapter)

    assert queue.status == "READY_FOR_RESEARCH"
    assert queue.ready_task_count == 1
    assert queue.evidence_pending_task_count == 0
    assert queue.tasks[0].status.value == "READY_FOR_RESEARCH"


def test_virtual_market_runtime_renders_improvement_experiment_task_queue_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:task-queue:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_experiment_task_queue_markdown(
        adapter
    )

    assert "Virtual Improvement Task Queue RESEARCH" in markdown
    assert "READY_FOR_RESEARCH" in markdown
    assert "Ready task count" in markdown


def test_virtual_market_runtime_publishes_improvement_experiment_task_queue(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:task-queue:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_experiment_task_queue(
        adapter,
        root=tmp_path,
        stamp="20260825T120000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_task_queue"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_FOR_RESEARCH" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Task Queue RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_work_planner() -> None:
    surface = research_surface_for_staging("snapshot:queue:planner:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    planner = VirtualMarketRuntime.build_improvement_research_work_planner(adapter)

    assert planner.status == "READY_PLAN"
    assert planner.selected_ready_task_ids
    assert planner.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_market_runtime_renders_improvement_research_work_planner_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:planner:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_research_work_planner_markdown(
        adapter
    )

    assert "Virtual Improvement Research Planner RESEARCH" in markdown
    assert "READY_PLAN" in markdown
    assert "START_BOUNDED_RESEARCH_EXPERIMENT" in markdown


def test_virtual_market_runtime_publishes_improvement_research_work_planner(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:planner:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_work_planner(
        adapter,
        root=tmp_path,
        stamp="20260825T130000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_work_planner"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_PLAN" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Research Planner RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_operator_handoff_summary() -> None:
    surface = research_surface_for_staging("snapshot:queue:handoff:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    summary = VirtualMarketRuntime.build_improvement_operator_handoff_summary(adapter)

    assert summary.status == "READY_HANDOFF"
    assert summary.selected_task_briefs
    assert summary.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_market_runtime_renders_improvement_operator_handoff_summary_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:handoff:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_operator_handoff_summary_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Operator Handoff RESEARCH" in markdown
    assert "READY_HANDOFF" in markdown
    assert "START_BOUNDED_RESEARCH_EXPERIMENT" in markdown


def test_virtual_market_runtime_publishes_improvement_operator_handoff_summary(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:handoff:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_operator_handoff_summary(
        adapter,
        root=tmp_path,
        stamp="20260825T140000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_operator_handoff"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_HANDOFF" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Operator Handoff RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_execution_inbox() -> None:
    surface = research_surface_for_staging("snapshot:queue:inbox:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    inbox = VirtualMarketRuntime.build_improvement_research_execution_inbox(adapter)

    assert inbox.status == "READY_INBOX"
    assert inbox.ready_work_items
    assert inbox.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_market_runtime_renders_improvement_research_execution_inbox_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:inbox:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_research_execution_inbox_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Research Inbox RESEARCH" in markdown
    assert "READY_INBOX" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_execution_inbox(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:inbox:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_execution_inbox(
        adapter,
        root=tmp_path,
        stamp="20260825T150000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_research_inbox"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_INBOX" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Research Inbox RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_execution_session_manifest() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    manifest = (
        VirtualMarketRuntime.build_improvement_research_execution_session_manifest(
            adapter
        )
    )

    assert manifest.status == "READY_SESSION"
    assert manifest.chosen_ready_item is not None
    assert manifest.action_order[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_market_runtime_renders_improvement_research_execution_session_manifest_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_research_execution_session_manifest_markdown(
        adapter
    )

    assert "Virtual Improvement Session Manifest RESEARCH" in markdown
    assert "READY_SESSION" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_execution_session_manifest(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = (
        VirtualMarketRuntime.publish_improvement_research_execution_session_manifest(
            adapter,
            root=tmp_path,
            stamp="20260825T160000Z",
        )
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_session_manifest"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_SESSION" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Session Manifest RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_session_journal() -> None:
    surface = research_surface_for_staging("snapshot:queue:session:journal:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    journal = VirtualMarketRuntime.build_improvement_research_session_journal(adapter)

    assert journal.status == "READY_JOURNAL"
    assert journal.chosen_ready_item is not None
    assert journal.closure_result == "READY_ITEM_SELECTED_FOR_RESEARCH"


def test_virtual_market_runtime_renders_improvement_research_session_journal_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:journal:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_research_session_journal_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Session Journal RESEARCH" in markdown
    assert "READY_JOURNAL" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_session_journal(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:journal:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_session_journal(
        adapter,
        root=tmp_path,
        stamp="20260825T170000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_session_journal"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "READY_JOURNAL" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Session Journal RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_session_closure_record() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:closure:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    closure = VirtualMarketRuntime.build_improvement_research_session_closure_record(
        adapter
    )

    assert closure.status == "COMPLETED_RESEARCH_ONLY"
    assert closure.chosen_ready_item is not None
    assert closure.closure_reason == "BOUNDED_RESEARCH_SESSION_RECORDED"


def test_virtual_market_runtime_renders_improvement_research_session_closure_record_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:closure:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_research_session_closure_record_markdown(
        adapter
    )

    assert "Virtual Improvement Session Closure RESEARCH" in markdown
    assert "COMPLETED_RESEARCH_ONLY" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_session_closure_record(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:closure:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_session_closure_record(
        adapter,
        root=tmp_path,
        stamp="20260825T180000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_session_closure"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "COMPLETED_RESEARCH_ONLY" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Session Closure RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_session_artifact_bundle() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:bundle:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    bundle = VirtualMarketRuntime.build_improvement_research_session_artifact_bundle(
        adapter
    )

    assert bundle.status == "INCOMPLETE_BUNDLE"
    assert bundle.missing_artifact_refs


def test_virtual_market_runtime_renders_improvement_research_session_artifact_bundle_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:bundle:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_research_session_artifact_bundle_markdown(
        adapter
    )

    assert "Virtual Improvement Session Bundle RESEARCH" in markdown
    assert "INCOMPLETE_BUNDLE" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_session_artifact_bundle(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:bundle:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_session_artifact_bundle(
        adapter,
        root=tmp_path,
        stamp="20260825T190000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_session_bundle"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "INCOMPLETE_BUNDLE" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Session Bundle RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_research_session_readiness_summary() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:readiness:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    summary = VirtualMarketRuntime.build_improvement_research_session_readiness_summary(
        adapter
    )

    assert summary.verdict == "EVIDENCE_GAP_REMAINING"
    assert summary.status == "BLOCKED_SUMMARY"
    assert "SESSION_ARTIFACT_GAP_REMAINING" in summary.blocker_codes


def test_virtual_market_runtime_renders_improvement_research_session_readiness_summary_markdown() -> (
    None
):
    surface = research_surface_for_staging(
        "snapshot:queue:session:readiness:markdown:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_research_session_readiness_summary_markdown(
        adapter
    )

    assert "Virtual Improvement Session Readiness RESEARCH" in markdown
    assert "BLOCKED_SUMMARY" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_research_session_readiness_summary(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:readiness:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_research_session_readiness_summary(
        adapter,
        root=tmp_path,
        stamp="20260825T200000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_session_readiness"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "BLOCKED_SUMMARY" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Session Readiness RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_next_candidate_intake_handoff() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:intake:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    handoff = VirtualMarketRuntime.build_improvement_next_candidate_intake_handoff(
        adapter
    )

    assert handoff.status == "BLOCKED_INTAKE"
    assert handoff.intake_decision == "HOLD_CURRENT_CYCLE"
    assert "SESSION_ARTIFACT_GAP_REMAINING" in handoff.blocker_codes


def test_virtual_market_runtime_renders_improvement_next_candidate_intake_handoff_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:intake:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_next_candidate_intake_handoff_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Next Candidate Intake RESEARCH" in markdown
    assert "BLOCKED_INTAKE" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_next_candidate_intake_handoff(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:intake:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_next_candidate_intake_handoff(
        adapter,
        root=tmp_path,
        stamp="20260825T210000Z",
    )

    assert (
        paths.report_dir
        == tmp_path
        / "runtime"
        / "reports"
        / "virtual_improvement_next_candidate_intake"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "BLOCKED_INTAKE" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Next Candidate Intake RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_next_candidate_refusal_artifact() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:refusal:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    artifact = VirtualMarketRuntime.build_improvement_next_candidate_refusal_artifact(
        adapter
    )

    assert artifact.status == "REFUSE_NEXT_CANDIDATE"
    assert artifact.refusal_reason == "NEXT_CANDIDATE_NOT_READY"


def test_virtual_market_runtime_renders_improvement_next_candidate_refusal_artifact_markdown() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:refusal:markdown:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_next_candidate_refusal_artifact_markdown(
        adapter
    )

    assert "Virtual Improvement Refusal Artifact RESEARCH" in markdown
    assert "REFUSE_NEXT_CANDIDATE" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_next_candidate_refusal_artifact(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:refusal:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_next_candidate_refusal_artifact(
        adapter,
        root=tmp_path,
        stamp="20260825T220000Z",
    )

    assert (
        paths.report_dir
        == tmp_path
        / "runtime"
        / "reports"
        / "virtual_improvement_next_candidate_refusal"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REFUSE_NEXT_CANDIDATE" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Refusal Artifact RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_publishes_improvement_next_candidate_registration_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = research_surface_for_staging(
        "snapshot:queue:session:registration:publish:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    monkeypatch.setattr(
        VirtualMarketRuntime,
        "build_improvement_next_candidate_intake_handoff",
        staticmethod(
            lambda _adapter: VirtualImprovementNextCandidateIntakeHandoff(
                handoff_id="handoff:ready-runtime",
                summary_id="summary:ready-runtime",
                bundle_id="bundle:ready-runtime",
                queue_id="queue:ready-runtime",
                snapshot_id="snapshot:ready-runtime",
                surface_kind="RESEARCH",
                status="READY_INTAKE",
                intake_decision="OPEN_NEXT_CANDIDATE",
                blocker_codes=(),
                required_follow_up="REGISTER_NEXT_VIRTUAL_CANDIDATE",
            )
        ),
    )

    paths = VirtualMarketRuntime.publish_improvement_next_candidate_registration_packet(
        adapter,
        root=tmp_path,
        stamp="20260825T221500Z",
    )

    assert (
        paths.report_dir
        == tmp_path
        / "runtime"
        / "reports"
        / "virtual_improvement_next_candidate_registration"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REGISTER_NEXT_CANDIDATE" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Registration Packet RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_refusal_ledger_entry() -> None:
    surface = research_surface_for_staging("snapshot:queue:session:refusal-ledger:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    entry = VirtualMarketRuntime.build_improvement_refusal_ledger_entry(adapter)

    assert entry.status == "REFUSAL_RECORDED"
    assert entry.refusal_reason == "NEXT_CANDIDATE_NOT_READY"


def test_virtual_market_runtime_renders_improvement_refusal_ledger_entry_markdown() -> (
    None
):
    surface = research_surface_for_staging(
        "snapshot:queue:session:refusal-ledger:markdown:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_refusal_ledger_entry_markdown(
        adapter
    )

    assert "Virtual Improvement Refusal Ledger RESEARCH" in markdown
    assert "REFUSAL_RECORDED" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_refusal_ledger_entry(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging(
        "snapshot:queue:session:refusal-ledger:publish:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_refusal_ledger_entry(
        adapter,
        root=tmp_path,
        stamp="20260825T223000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_refusal_ledger"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REFUSAL_RECORDED" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Refusal Ledger RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_publishes_improvement_candidate_registry_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:registry:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    monkeypatch.setattr(
        VirtualMarketRuntime,
        "build_improvement_next_candidate_intake_handoff",
        staticmethod(
            lambda _adapter: VirtualImprovementNextCandidateIntakeHandoff(
                handoff_id="handoff:registry-ready",
                summary_id="summary:registry-ready",
                bundle_id="bundle:registry-ready",
                queue_id="queue:registry-ready",
                snapshot_id="snapshot:registry-ready",
                surface_kind="RESEARCH",
                status="READY_INTAKE",
                intake_decision="OPEN_NEXT_CANDIDATE",
                blocker_codes=(),
                required_follow_up="REGISTER_NEXT_VIRTUAL_CANDIDATE",
            )
        ),
    )

    paths = VirtualMarketRuntime.publish_improvement_candidate_registry_entry(
        adapter,
        root=tmp_path,
        stamp="20260825T224500Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_candidate_registry"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "CANDIDATE_REGISTERED" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Candidate Registry RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_candidate_lifecycle_snapshot() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:lifecycle:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    snapshot = VirtualMarketRuntime.build_improvement_candidate_lifecycle_snapshot(
        adapter
    )

    assert snapshot.lifecycle_state == "REFUSED"
    assert snapshot.source_kind == "REFUSAL_LEDGER"


def test_virtual_market_runtime_renders_improvement_candidate_lifecycle_snapshot_markdown() -> (
    None
):
    surface = research_surface_for_staging(
        "snapshot:queue:session:lifecycle:markdown:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = (
        VirtualMarketRuntime.render_improvement_candidate_lifecycle_snapshot_markdown(
            adapter
        )
    )

    assert "Virtual Improvement Lifecycle Snapshot RESEARCH" in markdown
    assert "REFUSED" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_candidate_lifecycle_snapshot(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:lifecycle:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_candidate_lifecycle_snapshot(
        adapter,
        root=tmp_path,
        stamp="20260825T230000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_candidate_lifecycle"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REFUSED" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Lifecycle Snapshot RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_candidate_outcome_dashboard_payload() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:dashboard:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    dashboard = (
        VirtualMarketRuntime.build_improvement_candidate_outcome_dashboard_payload(
            adapter
        )
    )

    assert dashboard.outcome_state == "REFUSED"
    assert dashboard.blocker_count == 1
    assert dashboard.follow_up_category == "ARTIFACT_GAP_CLOSURE"


def test_virtual_market_runtime_renders_improvement_candidate_outcome_dashboard_payload_markdown() -> (
    None
):
    surface = research_surface_for_staging(
        "snapshot:queue:session:dashboard:markdown:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_candidate_outcome_dashboard_payload_markdown(
        adapter
    )

    assert "Virtual Improvement Outcome Dashboard RESEARCH" in markdown
    assert "REFUSED" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_candidate_outcome_dashboard_payload(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:dashboard:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = (
        VirtualMarketRuntime.publish_improvement_candidate_outcome_dashboard_payload(
            adapter,
            root=tmp_path,
            stamp="20260825T231500Z",
        )
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_outcome_dashboard"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REFUSED" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Outcome Dashboard RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_builds_improvement_candidate_cycle_executive_summary() -> (
    None
):
    surface = research_surface_for_staging("snapshot:queue:session:executive:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    summary = VirtualMarketRuntime.build_improvement_candidate_cycle_executive_summary(
        adapter
    )

    assert summary.outcome_state == "REFUSED"
    assert summary.next_action == "CLOSE_ARTIFACT_GAPS_OR_REVIEW_ESCALATIONS"
    assert summary.blocker_count == 1


def test_virtual_market_runtime_renders_improvement_candidate_cycle_executive_summary_markdown() -> (
    None
):
    surface = research_surface_for_staging(
        "snapshot:queue:session:executive:markdown:1"
    )
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    markdown = VirtualMarketRuntime.render_improvement_candidate_cycle_executive_summary_markdown(
        adapter
    )

    assert "Virtual Improvement Executive Summary RESEARCH" in markdown
    assert "REFUSED" in markdown
    assert "Tuesday, August 25, 2026" in markdown


def test_virtual_market_runtime_publishes_improvement_candidate_cycle_executive_summary(
    tmp_path: Path,
) -> None:
    surface = research_surface_for_staging("snapshot:queue:session:executive:publish:1")
    adapter = VirtualMarketRuntime.adapt_evidence_surface(surface)

    paths = VirtualMarketRuntime.publish_improvement_candidate_cycle_executive_summary(
        adapter,
        root=tmp_path,
        stamp="20260825T233000Z",
    )

    assert (
        paths.report_dir
        == tmp_path / "runtime" / "reports" / "virtual_improvement_executive_summary"
    )
    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert paths.latest_json_path.exists()
    assert paths.latest_markdown_path.exists()
    assert "REFUSED" in paths.json_path.read_text(encoding="utf-8")
    assert "Virtual Improvement Executive Summary RESEARCH" in (
        paths.markdown_path.read_text(encoding="utf-8")
    )


def test_virtual_market_runtime_honors_time_and_forced_exit_reasons() -> None:
    runtime = VirtualMarketRuntime()
    portfolio = VirtualPortfolioState(
        portfolio_id="virtual:spot:lifecycle:3",
        market="SPOT",
        cash_usdt=Decimal("900"),
        equity_usdt=Decimal("1000"),
        inventory_quantity=Decimal("1"),
        inventory_cost_basis_usdt=Decimal("100"),
        open_position_count=1,
    )
    timed_position = VirtualManagedPosition(
        position_id="virtual-position-3",
        candidate_id="candidate-3",
        symbol="HOTUSDT",
        market="SPOT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.1"),
        initial_quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        atr=Decimal("2"),
        take_profit_levels=(Decimal("120"),),
        maximum_holding_bars=1,
        bars_held=1,
        tick_size=Decimal("0.1"),
    )
    timed = runtime.process_position(
        position=timed_position,
        portfolio=portfolio,
        candle=lifecycle_candle(2, "100", "101", "99", "100"),
    )
    forced = runtime.process_position(
        position=replace(timed_position, bars_held=0, maximum_holding_bars=None),
        portfolio=portfolio,
        candle=lifecycle_candle(1, "100", "101", "99", "100"),
        context=VirtualExitContext(structure_invalidation=True),
    )

    assert timed.exit_reason is BacktestExitReason.TIME_EXIT
    assert timed.position_after.closure_review is not None
    assert (
        timed.position_after.closure_review.exit_reason is BacktestExitReason.TIME_EXIT
    )
    assert forced.exit_reason is BacktestExitReason.STRUCTURE_INVALIDATION
    assert forced.position_after.closure_review is not None
    assert (
        forced.position_after.closure_review.exit_reason
        is BacktestExitReason.STRUCTURE_INVALIDATION
    )


def test_virtual_managed_position_rejects_futures_without_margin_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="Futures virtual managed position requires complete margin evidence",
    ):
        VirtualManagedPosition(
            position_id="virtual-position-unsupported",
            candidate_id="candidate-unsupported",
            symbol="HOTUSDT",
            market="USD_M_FUTURES",
            opened_at=NOW,
            entry_price=Decimal("100"),
            entry_fee_usdt=Decimal("0.1"),
            initial_quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            stop_loss=Decimal("95"),
            trailing_stop=Decimal("95"),
            atr=Decimal("2"),
            take_profit_levels=(Decimal("120"),),
            tick_size=Decimal("0.1"),
        )


def test_virtual_market_runtime_calculates_portfolio_performance_from_regular_equity_samples() -> (
    None
):
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=(
            equity_point(0, "1000"),
            equity_point(1, "1010"),
            equity_point(2, "1005"),
            equity_point(3, "1030"),
        ),
    )

    assert isinstance(performance, VirtualPortfolioPerformance)
    assert performance.market == "SPOT"
    assert performance.net_return == Decimal("0.03")
    assert performance.annualized_return is not None
    assert performance.max_drawdown == Decimal("0.004950495049504950495049504950")
    assert performance.portfolio_sharpe is not None
    assert performance.portfolio_sortino is not None
    assert performance.sample_period_seconds == 86400


def test_virtual_market_runtime_rejects_unsupported_performance_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual portfolio performance market must be SPOT or USD_M_FUTURES",
    ):
        VirtualMarketRuntime.calculate_portfolio_performance(
            market="OPTIONS",
            equity_curve=(equity_point(0, "1000"), equity_point(1, "1005")),
        )


def test_virtual_market_equity_metrics_helpers_match_runtime_calculations() -> None:
    curve = (
        equity_point(0, "1000"),
        equity_point(1, "1010"),
        equity_point(2, "1005"),
        equity_point(3, "1030"),
    )
    equity_curve = cast(Sequence[EquityObservation], curve)
    returns = calculate_equity_returns(equity_curve)

    assert calculate_regular_sample_seconds(equity_curve) == 86400
    assert returns == (
        Decimal("0.01"),
        Decimal("-0.004950495049504950495049505"),
        Decimal("0.02487562189054726368159204"),
    )
    assert calculate_equity_max_drawdown(equity_curve) == Decimal(
        "0.004950495049504950495049504950"
    )
    assert calculate_periodic_sharpe(returns, periods_per_year=365.0) is not None
    assert calculate_periodic_sortino(returns, periods_per_year=365.0) is not None
    assert (
        calculate_annualized_return(
            curve[0].equity_usdt,
            curve[-1].equity_usdt,
            duration_seconds=86400 * 3,
        )
        is not None
    )


def test_virtual_market_performance_helper_matches_runtime_calculations() -> None:
    curve = (
        equity_point(0, "1000"),
        equity_point(1, "1010"),
        equity_point(2, "1005"),
        equity_point(3, "1030"),
    )
    helper_metrics = calculate_virtual_portfolio_performance_metrics(
        market="SPOT",
        equity_curve=cast(Sequence[EquityObservation], curve),
    )
    runtime_metrics = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=curve,
    )

    assert helper_metrics.market == runtime_metrics.market
    assert helper_metrics.starting_equity_usdt == runtime_metrics.starting_equity_usdt
    assert helper_metrics.ending_equity_usdt == runtime_metrics.ending_equity_usdt
    assert helper_metrics.observation_count == runtime_metrics.observation_count
    assert helper_metrics.sample_period_seconds == runtime_metrics.sample_period_seconds
    assert helper_metrics.net_return == runtime_metrics.net_return
    assert helper_metrics.annualized_return == runtime_metrics.annualized_return
    assert helper_metrics.max_drawdown == runtime_metrics.max_drawdown
    assert helper_metrics.portfolio_sharpe == runtime_metrics.portfolio_sharpe
    assert helper_metrics.portfolio_sortino == runtime_metrics.portfolio_sortino


def test_virtual_portfolio_performance_helper_rejects_empty_equity_curve() -> None:
    with pytest.raises(
        ValueError,
        match="virtual portfolio performance requires equity observations",
    ):
        calculate_virtual_portfolio_performance_metrics(
            market="SPOT",
            equity_curve=cast(Sequence[EquityObservation], ()),
        )


def test_virtual_market_runtime_rejects_irregular_equity_sampling() -> None:
    with pytest.raises(ValueError, match="regular sampling interval"):
        VirtualMarketRuntime.calculate_portfolio_performance(
            market="SPOT",
            equity_curve=(
                equity_point(0, "1000"),
                DailyEquityPoint(NOW + timedelta(days=2), Decimal("1010")),
                DailyEquityPoint(NOW + timedelta(days=5), Decimal("1020")),
            ),
        )


def test_virtual_market_runtime_handles_single_observation_without_annualization() -> (
    None
):
    performance = VirtualMarketRuntime.calculate_portfolio_performance(
        market="USD_M_FUTURES",
        equity_curve=(equity_point(0, "1000"),),
    )

    assert performance.net_return == Decimal("0")
    assert performance.annualized_return is None
    assert performance.portfolio_sharpe is None
    assert performance.portfolio_sortino is None
    assert performance.max_drawdown == Decimal("0")


def test_virtual_portfolio_state_rejects_unsupported_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual portfolio market must be SPOT or USD_M_FUTURES",
    ):
        VirtualPortfolioState(
            portfolio_id="virtual:unsupported:1",
            market="OPTIONS",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        )


def test_independent_virtual_portfolios_require_distinct_market_capital() -> None:
    spot = VirtualPortfolioState(
        portfolio_id="virtual:spot:1",
        market="SPOT",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )
    futures = VirtualPortfolioState(
        portfolio_id="virtual:futures:1",
        market="USD_M_FUTURES",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )

    pair = IndependentVirtualPortfolios(spot=spot, futures=futures)

    assert pair.spot.portfolio_id != pair.futures.portfolio_id
    with pytest.raises(ValueError, match="must stay independent"):
        IndependentVirtualPortfolios(
            spot=spot,
            futures=VirtualPortfolioState(
                portfolio_id="virtual:spot:1",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )


def test_virtual_market_runtime_opens_futures_long_with_margin_and_funding_evidence() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:1",
            decision_id="dge:fut:1",
            candidate_id="candidate:fut:1",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.BUY,
            quantity=Decimal("2"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            position_side=VirtualPositionSide.LONG,
            mark_price=Decimal("102"),
            funding_rate=Decimal("0.001"),
            leverage=5,
            isolated_margin_usdt=Decimal("50"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:1",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.trade_intent is not None
    assert decision.trade_intent.position_side is VirtualPositionSide.LONG
    assert decision.portfolio_after.position_side is VirtualPositionSide.LONG
    assert decision.portfolio_after.initial_margin_usdt == Decimal("40")
    assert decision.portfolio_after.maintenance_margin_usdt == Decimal("4")
    assert decision.portfolio_after.unrealized_pnl_usdt == Decimal("4")
    assert decision.portfolio_after.funding_cost_usdt == Decimal("0.200")
    assert decision.portfolio_after.liquidation_price == Decimal("77")


def test_virtual_market_runtime_opens_futures_short_with_mirrored_geometry() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:2",
            decision_id="dge:fut:2",
            candidate_id="candidate:fut:2",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.SELL,
            quantity=Decimal("2"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            take_profit_levels=(Decimal("90"),),
            position_side=VirtualPositionSide.SHORT,
            mark_price=Decimal("98"),
            funding_rate=Decimal("0.001"),
            leverage=5,
            isolated_margin_usdt=Decimal("50"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:2",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.trade_intent is not None
    assert decision.trade_intent.position_side is VirtualPositionSide.SHORT
    assert decision.portfolio_after.position_side is VirtualPositionSide.SHORT
    assert decision.portfolio_after.unrealized_pnl_usdt == Decimal("4")
    assert decision.portfolio_after.funding_cost_usdt == Decimal("-0.200")
    assert decision.portfolio_after.liquidation_price == Decimal("123")


@pytest.mark.parametrize(
    ("action", "side", "stop", "target", "high", "low"),
    [
        (
            Action.BUY,
            VirtualPositionSide.LONG,
            "95",
            "110",
            "111",
            "99",
        ),
        (
            Action.SELL,
            VirtualPositionSide.SHORT,
            "105",
            "90",
            "101",
            "89",
        ),
    ],
)
def test_virtual_market_runtime_closes_futures_positions_with_canonical_accounting(
    action: Action,
    side: VirtualPositionSide,
    stop: str,
    target: str,
    high: str,
    low: str,
) -> None:
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id=f"snapshot:futures:lifecycle:{side.value.lower()}",
        decision_id=f"dge:futures:lifecycle:{side.value.lower()}",
        candidate_id=f"candidate:futures:lifecycle:{side.value.lower()}",
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
        action=action,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal(stop),
        take_profit_levels=(Decimal(target),),
        position_side=side,
        mark_price=Decimal("100"),
        funding_rate=Decimal("0.001"),
        funding_payment_due=True,
        leverage=5,
        isolated_margin_usdt=Decimal("30"),
        maintenance_margin_ratio=Decimal("0.02"),
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0.0005"),
        portfolio=VirtualPortfolioState(
            portfolio_id=f"virtual:futures:lifecycle:{side.value.lower()}",
            market="USD_M_FUTURES",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    entry = runtime.evaluate(request)
    position = runtime.materialize_managed_position(
        request=request,
        decision=entry,
        opened_at=NOW,
    )

    closed = runtime.process_position(
        position=position,
        portfolio=entry.portfolio_after,
        candle=lifecycle_candle(1, "100", high, low, target),
        futures_context=VirtualFuturesPositionContext(
            observed_at=NOW + timedelta(hours=1),
            mark_price=Decimal(target),
            funding_rate=Decimal("0.002"),
            funding_payment_due=True,
        ),
    )

    assert closed.exit_reason is BacktestExitReason.TARGET
    assert closed.position_after.status is VirtualPositionLifecycleStatus.CLOSED
    assert closed.portfolio_after.open_position_count == 0
    assert closed.portfolio_after.position_side is None
    assert closed.portfolio_after.equity_usdt == closed.portfolio_after.cash_usdt
    assert closed.closed_trade is not None
    assert closed.closed_trade.direction.value == side.value
    assert closed.closed_trade.funding_cost_usdt == (
        closed.position_after.funding_cost_usdt
    )
    assert closed.closed_trade.net_pnl_usdt == (
        closed.portfolio_after.realized_pnl_usdt
    )
    assert closed.closed_trade.net_pnl_usdt == (
        closed.closed_trade.gross_pnl_usdt
        - closed.closed_trade.fee_cost_usdt
        - closed.closed_trade.slippage_cost_usdt
        - closed.closed_trade.funding_cost_usdt
    )


def test_virtual_market_runtime_prioritizes_futures_liquidation_and_charges_fee() -> (
    None
):
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:futures:liquidation",
        decision_id="dge:futures:liquidation",
        candidate_id="candidate:futures:liquidation",
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("80"),
        take_profit_levels=(Decimal("110"),),
        position_side=VirtualPositionSide.LONG,
        mark_price=Decimal("100"),
        funding_rate=Decimal("0"),
        funding_payment_due=False,
        leverage=5,
        isolated_margin_usdt=Decimal("30"),
        maintenance_margin_ratio=Decimal("0.02"),
        liquidation_fee_ratio=Decimal("0.005"),
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0"),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:futures:liquidation",
            market="USD_M_FUTURES",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    entry = runtime.evaluate(request)
    position = runtime.materialize_managed_position(
        request=request,
        decision=entry,
        opened_at=NOW,
    )
    liquidation_price = cast(Decimal, position.liquidation_price)

    closed = runtime.process_position(
        position=position,
        portfolio=entry.portfolio_after,
        candle=lifecycle_candle(1, "100", "120", "60", "100"),
        futures_context=VirtualFuturesPositionContext(
            observed_at=NOW + timedelta(hours=1),
            mark_price=liquidation_price,
            funding_rate=Decimal("0"),
        ),
    )

    assert closed.exit_reason is BacktestExitReason.LIQUIDATION
    assert closed.position_after.closure_review is not None
    assert closed.position_after.closure_review.stop_quality == "LIQUIDATED"
    assert closed.position_after.exits[-1].fee_usdt == (
        liquidation_price * Decimal("0.006")
    )
    assert closed.closed_trade is not None
    assert closed.closed_trade.exit_reason is BacktestExitReason.LIQUIDATION


def test_virtual_market_runtime_rejects_futures_lifecycle_without_context() -> None:
    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:futures:context",
        decision_id="dge:futures:context",
        candidate_id="candidate:futures:context",
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        position_side=VirtualPositionSide.LONG,
        mark_price=Decimal("100"),
        funding_rate=Decimal("0"),
        leverage=5,
        isolated_margin_usdt=Decimal("30"),
        maintenance_margin_ratio=Decimal("0.02"),
        portfolio=VirtualPortfolioState(
            portfolio_id="virtual:futures:context",
            market="USD_M_FUTURES",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    entry = runtime.evaluate(request)
    position = runtime.materialize_managed_position(
        request=request,
        decision=entry,
        opened_at=NOW,
    )

    with pytest.raises(ValueError, match="requires mark and funding context"):
        runtime.process_position(
            position=position,
            portfolio=entry.portfolio_after,
            candle=lifecycle_candle(1, "100", "101", "99", "100"),
        )


def test_virtual_market_runtime_blocks_futures_entry_on_margin_utilization_and_leverage() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:gov:1",
            decision_id="dge:fut:gov:1",
            candidate_id="candidate:fut:gov:1",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            position_side=VirtualPositionSide.LONG,
            mark_price=Decimal("100"),
            funding_rate=Decimal("0.001"),
            leverage=8,
            isolated_margin_usdt=Decimal("30"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio_governor=VirtualPortfolioRiskGovernor(
                maximum_margin_utilization_ratio=Decimal("0.50"),
                maximum_futures_leverage=5,
            ),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:gov:1",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
                position_side=VirtualPositionSide.LONG,
                position_entry_price=Decimal("100"),
                position_mark_price=Decimal("100"),
                position_notional_usdt=Decimal("100"),
                isolated_margin_usdt=Decimal("50"),
                initial_margin_usdt=Decimal("20"),
                maintenance_margin_usdt=Decimal("2"),
                liquidation_price=Decimal("52"),
                leverage=5,
                margin_utilization_ratio=Decimal("0.55"),
                open_position_count=1,
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "FUTURES_MARGIN_UTILIZATION_LIMIT_EXCEEDED" in decision.eligibility.blockers
    assert "FUTURES_LEVERAGE_LIMIT_EXCEEDED" in decision.eligibility.blockers


def test_virtual_market_runtime_applies_tick_step_and_spread_to_futures_entry() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:round:1",
            decision_id="dge:fut:round:1",
            candidate_id="candidate:fut:round:1",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.BUY,
            quantity=Decimal("2.34"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("112"),),
            half_spread_ratio=Decimal("0.0005"),
            tick_size=Decimal("0.1"),
            step_size=Decimal("0.1"),
            position_side=VirtualPositionSide.LONG,
            mark_price=Decimal("102"),
            funding_rate=Decimal("0.001"),
            leverage=5,
            isolated_margin_usdt=Decimal("60"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:round:1",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.ORDER_READY
    assert decision.trade_intent is not None
    assert decision.trade_intent.quantity == Decimal("2.3")
    assert decision.trade_intent.entry_price == Decimal("100.1")
    assert decision.portfolio_after.position_entry_price == Decimal("100.1")
    assert decision.portfolio_after.initial_margin_usdt == Decimal("46.046")
    assert decision.portfolio_after.unrealized_pnl_usdt == Decimal("4.37")


def test_virtual_market_runtime_fail_closes_futures_without_funding_evidence() -> None:
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:3",
            decision_id="dge:fut:3",
            candidate_id="candidate:fut:3",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            position_side=VirtualPositionSide.LONG,
            mark_price=Decimal("100"),
            leverage=5,
            isolated_margin_usdt=Decimal("30"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:3",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "FUNDING_DATA_UNAVAILABLE" in decision.eligibility.blockers


def test_virtual_market_runtime_fail_closes_futures_short_geometry_for_long_rules() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:4",
            decision_id="dge:fut:4",
            candidate_id="candidate:fut:4",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            position_side=VirtualPositionSide.SHORT,
            mark_price=Decimal("99"),
            funding_rate=Decimal("0.001"),
            leverage=5,
            isolated_margin_usdt=Decimal("30"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:4",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "FUTURES_SHORT_GEOMETRY_INVALID" in decision.eligibility.blockers


def test_virtual_market_runtime_fail_closes_futures_when_margin_is_insufficient() -> (
    None
):
    runtime = VirtualMarketRuntime()
    decision = runtime.evaluate(
        approved_virtual_runtime_request(
            snapshot_id="snapshot:fut:5",
            decision_id="dge:fut:5",
            candidate_id="candidate:fut:5",
            symbol="BTCUSDT",
            market="USD_M_FUTURES",
            action=Action.BUY,
            quantity=Decimal("2"),
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            position_side=VirtualPositionSide.LONG,
            mark_price=Decimal("100"),
            funding_rate=Decimal("0.001"),
            leverage=5,
            isolated_margin_usdt=Decimal("10"),
            maintenance_margin_ratio=Decimal("0.02"),
            portfolio=VirtualPortfolioState(
                portfolio_id="virtual:futures:5",
                market="USD_M_FUTURES",
                cash_usdt=Decimal("1000"),
                equity_usdt=Decimal("1000"),
            ),
        )
    )

    assert decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    assert "INSUFFICIENT_VIRTUAL_MARGIN" in decision.eligibility.blockers

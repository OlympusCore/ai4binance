"""Virtual runtime compatibility bridge contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import ModuleType
from typing import Any, cast

import pytest

import ai4binance.application as public_application
import ai4binance.application.services.virtual_runtime as virtual_runtime_bridge
import ai4binance.application.virtual_runtime as legacy_virtual_runtime
import ai4binance.research.virtual_runtime_attribution as legacy_attribution
from ai4binance.application.services.virtual_runtime import (
    VirtualMarketCycleResult,
    run_virtual_market_cycle,
)
from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
    VirtualSimulationStatus,
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.domain.research import (
    virtual_runtime_attribution as canonical_attribution,
)
from ai4binance.research import virtual_runtime as research_virtual_runtime
from ai4binance.research.virtual_runtime_attribution import (
    build_virtual_trade_attribution_ledger,
)


def test_virtual_runtime_research_all_is_explicit_contract() -> None:
    expected_exports = (
        "IndependentVirtualPortfolios",
        "VirtualAutonomyHaltStatus",
        "VirtualClosedTradeRecord",
        "VirtualClosureReview",
        "VirtualEvidenceSurfaceAdapter",
        "VirtualExitContext",
        "VirtualFillPreview",
        "VirtualFuturesPositionContext",
        "VirtualImprovementResearchQueue",
        "VirtualImprovementResearchWorkItem",
        "VirtualLossStreakHaltReview",
        "VirtualManagedPosition",
        "VirtualMarketRuntime",
        "VirtualNoTradeEvidenceSurface",
        "VirtualPortfolioPerformance",
        "VirtualPortfolioRiskGovernor",
        "VirtualPortfolioState",
        "VirtualPositionExit",
        "VirtualPositionLifecycleStatus",
        "VirtualPositionSide",
        "VirtualPositionUpdateDecision",
        "VirtualResearchEvidenceSurface",
        "VirtualRuntimeDecision",
        "VirtualRuntimeDecisionStatus",
        "VirtualRuntimeRequest",
        "VirtualStagedImprovementCandidate",
        "VirtualTradeAttributionAggregate",
        "VirtualTradeAttributionLedger",
        "VirtualTradeIntent",
    )
    assert research_virtual_runtime.__all__ == expected_exports


def test_virtual_runtime_research_public_exports_are_resolvable() -> None:
    missing_exports = [
        name
        for name in research_virtual_runtime.__all__
        if not hasattr(research_virtual_runtime, name)
    ]
    assert missing_exports == []


def test_virtual_runtime_attribution_extraction_preserves_result_identity() -> None:
    direct = build_virtual_trade_attribution_ledger(())
    through_facade = (
        research_virtual_runtime.VirtualMarketRuntime.build_trade_attribution_ledger(())
    )

    assert type(direct) is research_virtual_runtime.VirtualTradeAttributionLedger
    assert type(through_facade) is type(direct)
    assert through_facade == direct


def test_virtual_runtime_attribution_facades_preserve_canonical_identity() -> None:
    attribution_exports = (
        "BacktestExitReason",
        "ClosedTradeAttribution",
        "TradeDirection",
        "TradeEdgeAggregateView",
        "TradeEdgeLedger",
        "VirtualClosedTradeRecord",
        "VirtualTradeAttributionAggregate",
        "VirtualTradeAttributionLedger",
        "build_virtual_trade_attribution_ledger",
    )
    for name in attribution_exports:
        assert getattr(legacy_attribution, name) is getattr(canonical_attribution, name)

    application_exports = (
        "VirtualClosedTradeRecord",
        "VirtualTradeAttributionAggregate",
        "VirtualTradeAttributionLedger",
    )
    for name in application_exports:
        canonical = getattr(canonical_attribution, name)
        assert getattr(research_virtual_runtime, name) is canonical
        assert getattr(virtual_runtime_bridge, name) is canonical
        assert getattr(legacy_virtual_runtime, name) is canonical


def test_virtual_runtime_attribution_contracts_reject_invalid_identity_and_counts() -> (
    None
):
    with pytest.raises(ValueError, match="strategy_id is required"):
        canonical_attribution.ClosedTradeAttribution(strategy_id=" ")

    with pytest.raises(ValueError, match="at least one trade"):
        canonical_attribution.TradeEdgeAggregateView(
            trade_count=0,
            gross_pnl_usdt=Decimal("0"),
            fee_cost_usdt=Decimal("0"),
            slippage_cost_usdt=Decimal("0"),
            funding_cost_usdt=Decimal("0"),
            net_pnl_usdt=Decimal("0"),
            average_realized_r_multiple=Decimal("0"),
            average_maximum_favorable_excursion=Decimal("0"),
            average_maximum_adverse_excursion=Decimal("0"),
            average_holding_period=Decimal("0"),
        )

    with pytest.raises(ValueError, match="requires trades"):
        canonical_attribution.VirtualTradeAttributionAggregate(
            trade_count=0,
            net_pnl_usdt=Decimal("0"),
            expectancy_usdt=Decimal("0"),
            average_realized_r_multiple=Decimal("0"),
            fee_drag_usdt=Decimal("0"),
            slippage_drag_usdt=Decimal("0"),
            funding_drag_usdt=Decimal("0"),
            average_mfe=Decimal("0"),
            average_mae=Decimal("0"),
            false_breakout_rate=Decimal("0"),
            drawdown_contribution_usdt=Decimal("0"),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"trade_id": " "}, "identity is required"),
        ({"entry_reason": (" ",)}, "entry reason cannot contain blanks"),
        ({"dge_decision": " "}, "governance lineage is required"),
    ],
)
def test_virtual_closed_trade_rejects_incomplete_lineage(
    overrides: dict[str, object],
    message: str,
) -> None:
    valid = canonical_attribution.VirtualClosedTradeRecord(
        trade_id="trade-1",
        attribution=canonical_attribution.ClosedTradeAttribution(),
        direction=canonical_attribution.TradeDirection.LONG,
        entry_time=datetime(2026, 9, 11, tzinfo=UTC),
        exit_time=datetime(2026, 9, 11, 1, tzinfo=UTC),
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        quantity=Decimal("1"),
        risk_at_entry=Decimal("1"),
        entry_reason=("SETUP",),
        exit_reason=canonical_attribution.BacktestExitReason.TARGET,
        dge_decision="APPROVED_PAPER_ONLY",
        risk_policy_version="1",
        validation_version="1",
        gross_pnl_usdt=Decimal("1"),
        fee_cost_usdt=Decimal("0"),
        slippage_cost_usdt=Decimal("0"),
        funding_cost_usdt=Decimal("0"),
        net_pnl_usdt=Decimal("1"),
        realized_r_multiple=Decimal("1"),
        maximum_favorable_excursion=Decimal("1"),
        maximum_adverse_excursion=Decimal("0"),
    )
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(valid, **overrides)


def test_virtual_runtime_legacy_and_public_exports_preserve_canonical_identity() -> (
    None
):
    for name in virtual_runtime_bridge.__all__:
        assert getattr(legacy_virtual_runtime, name) is getattr(
            virtual_runtime_bridge, name
        )

    application_exports = (
        "VirtualMarketCycleResult",
        "VirtualMarketRuntime",
        "VirtualPortfolioState",
        "VirtualRuntimeDecision",
        "VirtualRuntimeDecisionStatus",
        "VirtualRuntimeRequest",
        "VirtualSimulationEligibility",
        "VirtualSimulationStatus",
        "VirtualTradeIntent",
        "evaluate_virtual_market_runtime",
        "run_virtual_market_cycle",
    )
    for name in application_exports:
        assert getattr(public_application, name) is getattr(
            virtual_runtime_bridge, name
        )

    assert VirtualMarketCycleResult.__module__ == (
        "ai4binance.application.services.virtual_runtime"
    )


def test_virtual_runtime_legacy_facade_preserves_public_contract() -> None:
    assert legacy_virtual_runtime.__all__ == virtual_runtime_bridge.__all__
    assert legacy_virtual_runtime.__dir__() == list(virtual_runtime_bridge.__all__)


def test_virtual_runtime_all_matches_bridge_contract() -> None:
    expected_exports = (
        "VirtualSimulationEligibility",
        "VirtualSimulationStatus",
        "evaluate_virtual_simulation_eligibility",
        "VirtualMarketCycleResult",
        "evaluate_virtual_market_runtime",
        "run_virtual_market_cycle",
        *research_virtual_runtime.__all__,
    )
    assert set(virtual_runtime_bridge.__all__) == set(expected_exports)
    assert len(virtual_runtime_bridge.__all__) == len(expected_exports)
    assert virtual_runtime_bridge.__dir__() == list(virtual_runtime_bridge.__all__)
    assert "_RESEARCH_EXPORTS" not in virtual_runtime_bridge.__dir__()
    assert "_research_virtual_runtime" not in virtual_runtime_bridge.__dir__()
    assert "__getattr__" not in virtual_runtime_bridge.__dir__()


def test_virtual_runtime_bridge_exports_are_resolvable() -> None:
    for name in research_virtual_runtime.__all__:
        value = getattr(virtual_runtime_bridge, name)
        assert value is getattr(research_virtual_runtime, name)
        assert vars(virtual_runtime_bridge)[name] is value


def test_virtual_runtime_bridge_rejects_private_research_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ai4binance.research.virtual_runtime")
    fake_module.__dict__["_hidden_bridge_only_symbol"] = object()
    monkeypatch.setattr(
        virtual_runtime_bridge,
        "_research_virtual_runtime",
        fake_module,
    )
    monkeypatch.setattr(
        virtual_runtime_bridge,
        "_RESEARCH_EXPORTS",
        {"VirtualMarketRuntime"},
    )

    with pytest.raises(AttributeError, match="has no attribute"):
        virtual_runtime_bridge.__getattr__("_hidden_bridge_only_symbol")


def test_virtual_runtime_exports_eligibility_contract() -> None:
    assert (
        virtual_runtime_bridge.VirtualSimulationEligibility
        is VirtualSimulationEligibility
    )
    assert virtual_runtime_bridge.VirtualSimulationStatus is VirtualSimulationStatus
    assert (
        virtual_runtime_bridge.evaluate_virtual_simulation_eligibility
        is evaluate_virtual_simulation_eligibility
    )
    assert "VirtualSimulationEligibility" in virtual_runtime_bridge.__dir__()
    assert "VirtualSimulationStatus" in virtual_runtime_bridge.__dir__()
    assert "evaluate_virtual_simulation_eligibility" in virtual_runtime_bridge.__dir__()
    assert "VirtualMarketCycleResult" in virtual_runtime_bridge.__dir__()
    assert "evaluate_virtual_market_runtime" in virtual_runtime_bridge.__dir__()
    assert "run_virtual_market_cycle" in virtual_runtime_bridge.__dir__()


def test_virtual_runtime_exports_cycle_result_contract() -> None:
    assert virtual_runtime_bridge.VirtualMarketCycleResult is VirtualMarketCycleResult
    assert virtual_runtime_bridge.run_virtual_market_cycle is run_virtual_market_cycle
    assert "VirtualMarketCycleResult" in virtual_runtime_bridge.__dir__()
    assert "run_virtual_market_cycle" in virtual_runtime_bridge.__dir__()


def test_virtual_market_cycle_result_bundle_is_live_blocked_only() -> None:
    request = object()
    execution_surface = type("ExecutionSurfaceLike", (), {"value": "VIRTUAL_MARKET"})()
    eligibility = VirtualSimulationEligibility(
        status=VirtualSimulationStatus.ELIGIBLE,
        execution_surface=execution_surface,
        requires_manual_confirmation=False,
        virtual_simulation_allowed=True,
        auto_simulation_allowed=True,
        binance_order_allowed=False,
        live_order_allowed=False,
        blockers=(),
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    decision = type(
        "VirtualRuntimeDecisionLike",
        (),
        {
            "eligibility": eligibility,
            "status": type("StatusLike", (), {"value": "ORDER_READY"})(),
            "halted": False,
            "trade_intent": None,
            "portfolio_before": object(),
            "portfolio_after": object(),
            "audit_refs": ("snapshot", "decision", "portfolio"),
            "halt_review": None,
        },
    )()
    runtime = type(
        "VirtualMarketRuntimeLike",
        (),
        {"evaluate": lambda self, _incoming_request: decision},
    )()

    result = run_virtual_market_cycle(request, runtime=runtime)

    assert result.request is request
    assert result.decision is decision
    assert result.eligibility is eligibility
    assert result.blockers == ()
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert cast(Any, result.decision_status).value == "ORDER_READY"
    assert result.halted is False
    assert result.to_payload()["request"] is request
    assert result.to_payload()["execution_allowed"] is False
    assert result.to_payload()["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_virtual_runtime_eligibility_exports_are_bridge_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ai4binance.research.virtual_runtime")
    monkeypatch.setattr(
        virtual_runtime_bridge,
        "_research_virtual_runtime",
        fake_module,
    )

    assert (
        virtual_runtime_bridge.__getattr__("VirtualSimulationEligibility")
        is VirtualSimulationEligibility
    )
    assert (
        virtual_runtime_bridge.__getattr__("VirtualSimulationStatus")
        is VirtualSimulationStatus
    )
    assert (
        virtual_runtime_bridge.__getattr__("evaluate_virtual_simulation_eligibility")
        is evaluate_virtual_simulation_eligibility
    )
    assert (
        virtual_runtime_bridge.__getattr__("evaluate_virtual_market_runtime")
        is virtual_runtime_bridge.evaluate_virtual_market_runtime
    )


def test_virtual_runtime_lazy_research_export_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ai4binance.research.virtual_runtime")
    sentinel = object()
    fake_module.__dict__["VirtualMarketRuntime"] = sentinel

    monkeypatch.setattr(
        virtual_runtime_bridge,
        "_research_virtual_runtime",
        fake_module,
    )
    monkeypatch.delattr(virtual_runtime_bridge, "VirtualMarketRuntime", raising=False)

    assert virtual_runtime_bridge.__getattr__("VirtualMarketRuntime") is sentinel
    assert vars(virtual_runtime_bridge)["VirtualMarketRuntime"] is sentinel
    assert "VirtualMarketRuntime" in virtual_runtime_bridge.__dir__()


def test_virtual_runtime_unknown_export_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute"):
        virtual_runtime_bridge.__getattr__("UnknownVirtualRuntimeExport")

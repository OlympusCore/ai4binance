"""Spot/Futures portfolio rebalancing agent tests."""

from decimal import Decimal

import pytest

from ai4binance.markets import CapitalMarket
from ai4binance.portfolio.rebalancing_agent import (
    MarketAllocationState,
    PortfolioRebalanceAction,
    PortfolioRebalancingAdvice,
    PortfolioRebalancingPolicy,
    PortfolioRebalancingReport,
    RebalancingAgent,
)


def state(
    market: CapitalMarket,
    *,
    position: str,
    liquid: str,
    risk_notional: str = "0",
) -> MarketAllocationState:
    return MarketAllocationState(
        market,
        Decimal(position),
        Decimal(liquid),
        Decimal(risk_notional),
    )


def test_rebalancing_agent_holds_at_target_90_10_with_liquidity() -> None:
    report = RebalancingAgent().review(
        spot=state(CapitalMarket.SPOT, position="800", liquid="100"),
        futures=state(
            CapitalMarket.USD_M_FUTURES,
            position="20",
            liquid="80",
            risk_notional="100",
        ),
    )

    assert report.current_spot_ratio == Decimal("0.9")
    assert report.current_futures_ratio == Decimal("0.1")
    assert report.spot_position_ratio == Decimal("0.8888888888888888888888888889")
    assert report.futures_liquid_ratio == Decimal("0.8")
    assert report.advice[0].action is PortfolioRebalanceAction.HOLD_REVIEW
    assert report.advice[0].approval_required is False
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_rebalancing_agent_recommends_futures_to_spot_when_overweight() -> None:
    report = RebalancingAgent().review(
        spot=state(CapitalMarket.SPOT, position="650", liquid="50"),
        futures=state(CapitalMarket.USD_M_FUTURES, position="100", liquid="200"),
    )

    transfer = next(
        item
        for item in report.advice
        if item.action is PortfolioRebalanceAction.TRANSFER_TO_SPOT_REVIEW
    )
    assert report.current_spot_ratio == Decimal("0.7")
    assert transfer.market is CapitalMarket.SPOT
    assert transfer.proposed_notional_usdt == Decimal("200.00")
    assert transfer.execution_allowed is False


def test_rebalancing_agent_flags_low_spot_and_futures_liquidity() -> None:
    report = RebalancingAgent().review(
        spot=state(CapitalMarket.SPOT, position="895", liquid="5"),
        futures=state(
            CapitalMarket.USD_M_FUTURES,
            position="80",
            liquid="20",
            risk_notional="450",
        ),
    )

    actions = {item.action for item in report.advice}
    assert PortfolioRebalanceAction.FREE_SPOT_LIQUIDITY_REVIEW in actions
    assert PortfolioRebalanceAction.REDUCE_FUTURES_RISK_REVIEW in actions
    futures = next(
        item
        for item in report.advice
        if item.action is PortfolioRebalanceAction.REDUCE_FUTURES_RISK_REVIEW
    )
    assert futures.proposed_notional_usdt == Decimal("50.0")
    assert "FUTURES_LIQUIDITY_RESERVE_LOW" in futures.blockers


def test_rebalancing_agent_blocks_invalid_evidence_without_execution() -> None:
    report = RebalancingAgent().review(
        spot=MarketAllocationState(
            CapitalMarket.SPOT,
            Decimal("0"),
            Decimal("0"),
            blockers=("SPOT_WALLET_UNAVAILABLE",),
        ),
        futures=MarketAllocationState(
            CapitalMarket.USD_M_FUTURES, Decimal("0"), Decimal("0")
        ),
    )

    assert report.blockers == (
        "SPOT_WALLET_UNAVAILABLE",
        "PORTFOLIO_VALUE_UNAVAILABLE",
    )
    assert report.advice[0].action is PortfolioRebalanceAction.BLOCKED
    assert report.execution_allowed is False


def test_rebalancing_policy_requires_90_10_sum_and_safe_ratios() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        PortfolioRebalancingPolicy(
            target_spot_ratio=Decimal("0.80"),
            target_futures_ratio=Decimal("0.10"),
        )
    with pytest.raises(ValueError, match="between zero and one"):
        PortfolioRebalancingPolicy(futures_min_liquid_ratio=Decimal("1.2"))


def test_rebalancing_agent_recommends_spot_to_futures_when_spot_overweight() -> None:
    report = RebalancingAgent().review(
        spot=state(CapitalMarket.SPOT, position="950", liquid="50"),
        futures=state(CapitalMarket.USD_M_FUTURES, position="0", liquid="0"),
    )

    transfer = next(
        item
        for item in report.advice
        if item.action is PortfolioRebalanceAction.TRANSFER_TO_FUTURES_REVIEW
    )
    assert report.current_spot_ratio == Decimal("1")
    assert transfer.market is CapitalMarket.USD_M_FUTURES
    assert transfer.proposed_notional_usdt == Decimal("100.00")
    assert (
        "FUTURES_TARGET_IS_CAPITAL_ALLOCATION_NOT_LEVERAGED_NOTIONAL"
        in transfer.blockers
    )


def test_rebalancing_agent_suppresses_tiny_allocation_transfer() -> None:
    report = RebalancingAgent(
        PortfolioRebalancingPolicy(minimum_transfer_usdt=Decimal("50"))
    ).review(
        spot=state(CapitalMarket.SPOT, position="815", liquid="100"),
        futures=state(CapitalMarket.USD_M_FUTURES, position="20", liquid="65"),
    )

    assert tuple(item.action for item in report.advice) == (
        PortfolioRebalanceAction.HOLD_REVIEW,
    )
    assert report.advice[0].approval_required is False


def test_rebalancing_agent_rejects_invalid_markets_and_contracts() -> None:
    with pytest.raises(ValueError, match="SPOT market"):
        RebalancingAgent().review(
            spot=state(CapitalMarket.USD_M_FUTURES, position="1", liquid="1"),
            futures=state(CapitalMarket.USD_M_FUTURES, position="1", liquid="1"),
        )
    with pytest.raises(ValueError, match="USD_M_FUTURES market"):
        RebalancingAgent().review(
            spot=state(CapitalMarket.SPOT, position="1", liquid="1"),
            futures=state(CapitalMarket.SPOT, position="1", liquid="1"),
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        MarketAllocationState(CapitalMarket.SPOT, Decimal("-1"), Decimal("0"))
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        MarketAllocationState(
            CapitalMarket.SPOT, Decimal("0"), Decimal("0"), blockers=("",)
        )
    with pytest.raises(ValueError, match="finite and positive"):
        PortfolioRebalancingPolicy(minimum_transfer_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="rationale is required"):
        PortfolioRebalancingAdvice(
            PortfolioRebalanceAction.HOLD_REVIEW,
            None,
            Decimal("0"),
            "",
        )
    with pytest.raises(ValueError, match="amount is invalid"):
        PortfolioRebalancingAdvice(
            PortfolioRebalanceAction.HOLD_REVIEW,
            None,
            Decimal("-1"),
            "manual review",
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        PortfolioRebalancingAdvice(
            PortfolioRebalanceAction.HOLD_REVIEW,
            None,
            Decimal("0"),
            "manual review",
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="report ratios are invalid"):
        PortfolioRebalancingReport(
            Decimal("0.9"),
            Decimal("0.1"),
            Decimal("1.1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            (),
            (),
        )
    with pytest.raises(ValueError, match="cannot allow execution"):
        PortfolioRebalancingReport(
            Decimal("0.9"),
            Decimal("0.1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            (),
            (),
            execution_allowed=True,
        )

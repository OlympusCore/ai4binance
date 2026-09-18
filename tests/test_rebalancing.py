"""Proposal-only Decimal inventory rebalancing tests."""

from decimal import Decimal

import pytest

from ai4binance.portfolio.rebalancing import (
    InventoryBuckets,
    RebalanceAction,
    RebalancePolicy,
    RebalanceProposal,
    RebalanceProposalEngine,
)


def buckets() -> InventoryBuckets:
    return InventoryBuckets(
        core_units=Decimal("60"),
        strategic_units=Decimal("30"),
        tactical_units=Decimal("10"),
        cash_quote=Decimal("100"),
    )


def test_sell_proposal_uses_rotation_inventory_and_never_grants_execution() -> None:
    report = RebalanceProposalEngine().propose(
        buckets(),
        RebalancePolicy(target_asset_ratio=Decimal("0.25")),
        price_quote=Decimal("1"),
        clock_index=10,
        requested_stage=1,
    )
    assert report.action is RebalanceAction.SELL
    assert report.proposed_notional_quote == Decimal("30.00")
    assert report.proposed_units == Decimal("30.00")
    assert report.estimated_fee_quote == Decimal("0.03000")
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_buy_proposal_respects_reserved_cash_and_trade_cap() -> None:
    wallet = InventoryBuckets(
        Decimal("10"),
        Decimal("0"),
        Decimal("0"),
        Decimal("190"),
        reserved_cash_quote=Decimal("170"),
    )
    report = RebalanceProposalEngine().propose(
        wallet,
        RebalancePolicy(target_asset_ratio=Decimal("0.80")),
        price_quote=Decimal("1"),
        clock_index=5,
        requested_stage=1,
    )
    assert report.action is RebalanceAction.BUY
    assert report.proposed_notional_quote == Decimal("20")


def test_hysteresis_cooldown_stage_and_risk_blockers_fail_closed() -> None:
    engine = RebalanceProposalEngine()
    hold = engine.propose(
        buckets(),
        RebalancePolicy(target_asset_ratio=Decimal("0.50")),
        price_quote=Decimal("1"),
        clock_index=1,
        requested_stage=0,
    )
    assert hold.action is RebalanceAction.HOLD
    assert hold.blockers == ("REBALANCE_HYSTERESIS_BAND",)
    staged = InventoryBuckets(
        Decimal("60"),
        Decimal("30"),
        Decimal("10"),
        Decimal("100"),
        last_stage=1,
        last_side="SELL",
        last_stage_clock=9,
    )
    blocked = engine.propose(
        staged,
        RebalancePolicy(target_asset_ratio=Decimal("0.90")),
        price_quote=Decimal("1"),
        clock_index=10,
        requested_stage=3,
        risk_blockers=("PORTFOLIO_GROSS_LIMIT_EXCEEDED",),
    )
    assert blocked.action is RebalanceAction.BLOCKED
    assert blocked.blockers == (
        "PORTFOLIO_GROSS_LIMIT_EXCEEDED",
        "REBALANCE_COOLDOWN_ACTIVE",
        "REBALANCE_STAGE_JUMP_BLOCKED",
        "REBALANCE_SIDE_TRANSITION_BLOCKED",
    )


def test_invalid_policy_and_price_are_rejected() -> None:
    with pytest.raises(ValueError, match="target asset"):
        RebalancePolicy(target_asset_ratio=Decimal("1.1"))
    with pytest.raises(ValueError, match="price"):
        RebalanceProposalEngine().propose(
            buckets(),
            RebalancePolicy(target_asset_ratio=Decimal("0.5")),
            price_quote=Decimal("0"),
            clock_index=0,
            requested_stage=0,
        )


def test_rebalance_contracts_reject_invalid_bucket_policy_and_proposal() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        InventoryBuckets(
            Decimal("-1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="reserved cash"):
        InventoryBuckets(
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
            reserved_cash_quote=Decimal("2"),
        )
    with pytest.raises(ValueError, match="stage state"):
        InventoryBuckets(
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
            last_side="ROTATE",
        )
    with pytest.raises(ValueError, match="minimum notional"):
        RebalancePolicy(
            target_asset_ratio=Decimal("0.5"),
            minimum_notional_quote=Decimal("0"),
        )
    with pytest.raises(ValueError, match="positive and at most one"):
        RebalancePolicy(
            target_asset_ratio=Decimal("0.5"),
            maximum_trade_ratio=Decimal("0"),
        )
    with pytest.raises(ValueError, match="stage policy"):
        RebalancePolicy(
            target_asset_ratio=Decimal("0.5"),
            cooldown_candles=-1,
        )
    with pytest.raises(ValueError, match="rebalance proposal is invalid"):
        RebalanceProposal(
            RebalanceAction.HOLD,
            Decimal("0"),
            Decimal("0.5"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            0,
            (),
            execution_allowed=True,
        )


def test_rebalance_engine_blocks_zero_value_minimum_notional_and_bad_stage() -> None:
    engine = RebalanceProposalEngine()
    zero_value = engine.propose(
        InventoryBuckets(
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ),
        RebalancePolicy(target_asset_ratio=Decimal("0.5")),
        price_quote=Decimal("1"),
        clock_index=0,
        requested_stage=0,
    )
    assert zero_value.action is RebalanceAction.BLOCKED
    assert zero_value.blockers == ("PORTFOLIO_VALUE_UNAVAILABLE",)

    minimum = engine.propose(
        InventoryBuckets(
            Decimal("10"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ),
        RebalancePolicy(
            target_asset_ratio=Decimal("0.1"),
            minimum_notional_quote=Decimal("20"),
        ),
        price_quote=Decimal("1"),
        clock_index=10,
        requested_stage=0,
    )
    assert minimum.action is RebalanceAction.BLOCKED
    assert minimum.blockers == ("REBALANCE_MINIMUM_NOTIONAL_BLOCKED",)
    with pytest.raises(ValueError, match="clock and stage"):
        engine.propose(
            buckets(),
            RebalancePolicy(target_asset_ratio=Decimal("0.5")),
            price_quote=Decimal("1"),
            clock_index=-1,
            requested_stage=0,
        )

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.portfolio.inventory_rotation import (
    InventoryRotationAction,
    InventoryRotationContext,
    InventoryRotationPhase,
    InventoryRotationPolicy,
    InventoryRotationProposalEngine,
    InventoryRotationState,
)
from ai4binance.portfolio.rebalancing import InventoryBuckets

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _buckets() -> InventoryBuckets:
    return InventoryBuckets(
        core_units=Decimal("60"),
        strategic_units=Decimal("25"),
        tactical_units=Decimal("15"),
        cash_quote=Decimal("1000"),
    )


def test_inventory_sell_rebuy_state_machine_requires_manual_confirmations() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-1", NOW)
    sell_context = InventoryRotationContext(
        price_quote=Decimal("1.20"),
        resistance_quote=Decimal("1.19"),
        support_quote=Decimal("0.90"),
        sell_trigger_confirmed=True,
        support_reclaimed=False,
        average_rotation_cost_quote=Decimal("1.00"),
    )

    sell = engine.review(initial, _buckets(), sell_context)
    assert sell.action is InventoryRotationAction.SELL
    assert sell.proposed_units == Decimal("10.00")
    assert sell.next_state.phase is InventoryRotationPhase.SELL_PROPOSED
    assert sell.execution_allowed is False

    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=Decimal("10"),
        realized_proceeds_quote=Decimal("11.98"),
        confirmed_at=NOW + timedelta(hours=1),
    )
    assert awaiting.phase is InventoryRotationPhase.AWAITING_REBUY

    rebuy = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("0.90"),
            resistance_quote=Decimal("1.19"),
            support_quote=Decimal("0.90"),
            sell_trigger_confirmed=False,
            support_reclaimed=True,
        ),
    )
    assert rebuy.action is InventoryRotationAction.BLOCKED
    assert rebuy.blockers == ("ROTATION_MINIMUM_NOTIONAL_BLOCKED",)


def test_inventory_rotation_preserves_core_and_fails_closed_on_risk() -> None:
    proposal = InventoryRotationProposalEngine().review(
        InventoryRotationState.new("rotation-2", NOW),
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("1.20"),
            resistance_quote=Decimal("1.19"),
            support_quote=Decimal("0.90"),
            sell_trigger_confirmed=True,
            support_reclaimed=False,
            average_rotation_cost_quote=Decimal("1.00"),
            risk_blockers=("DAILY_LOSS_LIMIT_ACTIVE",),
        ),
    )

    assert proposal.action is InventoryRotationAction.BLOCKED
    assert proposal.proposed_units == 0
    assert proposal.blockers == ("DAILY_LOSS_LIMIT_ACTIVE",)


def test_inventory_rotation_hold_rebuy_and_close_paths() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-3", NOW)
    hold = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("1.0"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.8"),
            sell_trigger_confirmed=False,
            support_reclaimed=False,
        ),
    )
    assert hold.action is InventoryRotationAction.HOLD
    assert len(hold.blockers) == 3

    sell = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("1.2"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.8"),
            sell_trigger_confirmed=True,
            support_reclaimed=False,
            average_rotation_cost_quote=Decimal("1.00"),
        ),
    )
    pending = engine.review(
        sell.next_state,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("1.2"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.8"),
            sell_trigger_confirmed=True,
            support_reclaimed=False,
            average_rotation_cost_quote=Decimal("1.00"),
        ),
    )
    assert pending.blockers == ("MANUAL_FILL_CONFIRMATION_REQUIRED",)
    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=sell.proposed_units,
        realized_proceeds_quote=sell.proposed_notional_quote,
        confirmed_at=NOW + timedelta(hours=1),
    )
    rebuy = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("0.9"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.9"),
            sell_trigger_confirmed=False,
            support_reclaimed=True,
        ),
        policy=InventoryRotationPolicy(
            maximum_rebuy_ratio_per_stage=Decimal("1"),
        ),
    )
    assert rebuy.action is InventoryRotationAction.REBUY
    closed = engine.confirm_rebuy(
        rebuy.next_state,
        quote_spent=rebuy.proposed_notional_quote,
        confirmed_at=NOW + timedelta(hours=2),
    )
    assert closed.phase is InventoryRotationPhase.CLOSED
    assert engine.review(
        closed,
        _buckets(),
        InventoryRotationContext(
            price_quote=Decimal("0.9"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.9"),
            sell_trigger_confirmed=False,
            support_reclaimed=True,
        ),
    ).blockers == ("ROTATION_CYCLE_CLOSED",)


def test_inventory_rotation_rejects_invalid_confirmations_and_context() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-4", NOW)
    with pytest.raises(ValueError, match="pending sell"):
        engine.confirm_sell(
            initial,
            filled_units=Decimal("1"),
            realized_proceeds_quote=Decimal("1"),
            confirmed_at=NOW,
        )
    with pytest.raises(ValueError, match="below resistance"):
        InventoryRotationContext(
            price_quote=Decimal("1"),
            resistance_quote=Decimal("0.8"),
            support_quote=Decimal("0.9"),
            sell_trigger_confirmed=False,
            support_reclaimed=False,
        )


def test_inventory_rotation_requires_cost_profit_floor_and_rebuy_band() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-cost", NOW)
    missing = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            Decimal("1.2"), Decimal("1.2"), Decimal("0.9"), True, False
        ),
    )
    below_floor = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            Decimal("1.02"),
            Decimal("1.02"),
            Decimal("0.9"),
            True,
            False,
            Decimal("1"),
        ),
    )
    assert "ROTATION_COST_BASIS_UNAVAILABLE" in missing.blockers
    assert "ROTATION_SELL_BELOW_COST_PROFIT_FLOOR" in below_floor.blockers

    sell = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            Decimal("1.2"), Decimal("1.2"), Decimal("0.9"), True, False, Decimal("1")
        ),
    )
    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=sell.proposed_units,
        realized_proceeds_quote=sell.proposed_notional_quote,
        confirmed_at=NOW + timedelta(hours=1),
    )
    too_low = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            Decimal("0.8"), Decimal("1.2"), Decimal("0.8"), False, True
        ),
    )
    assert "INVENTORY_REBUY_PRICE_BELOW_BAND" in too_low.blockers
    assert awaiting.rebuy_band_lower_quote == Decimal("0.84")
    assert awaiting.rebuy_band_upper_quote == Decimal("1.140")


def test_inventory_rotation_contracts_reject_invalid_band_and_policy() -> None:
    with pytest.raises(ValueError, match="rebuy band"):
        InventoryRotationState(
            "bad-band",
            InventoryRotationPhase.AWAITING_REBUY,
            NOW,
            rebuy_band_lower_quote=Decimal("1"),
            rebuy_band_upper_quote=Decimal("0.9"),
        )
    with pytest.raises(ValueError, match="discount band"):
        InventoryRotationPolicy(
            minimum_rebuy_discount_ratio=Decimal("0.4"),
            maximum_rebuy_discount_ratio=Decimal("0.3"),
        )
    with pytest.raises(ValueError, match="cost basis"):
        InventoryRotationContext(
            Decimal("1"),
            Decimal("1.2"),
            Decimal("0.8"),
            False,
            False,
            Decimal("0"),
        )


def test_inventory_rotation_rejects_overfilled_sell_and_rebuy() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-overfill", NOW)
    sell = engine.review(
        initial,
        _buckets(),
        InventoryRotationContext(
            Decimal("1.2"), Decimal("1.2"), Decimal("0.9"), True, False, Decimal("1")
        ),
    )
    with pytest.raises(ValueError, match="units exceed"):
        engine.confirm_sell(
            sell.next_state,
            filled_units=sell.proposed_units + Decimal("1"),
            realized_proceeds_quote=sell.proposed_notional_quote,
            confirmed_at=NOW,
        )
    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=sell.proposed_units,
        realized_proceeds_quote=sell.proposed_notional_quote,
        confirmed_at=NOW,
    )
    with pytest.raises(ValueError, match="pending proposal"):
        engine.confirm_rebuy(awaiting, quote_spent=Decimal("1"), confirmed_at=NOW)


@pytest.mark.parametrize(
    ("build_state", "message"),
    [
        (
            lambda: InventoryRotationState(
                cycle_id=" ",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
            ),
            "cycle identity",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=datetime(2026, 7, 16),
            ),
            "timezone-aware",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
                sold_units=Decimal("-1"),
            ),
            "values must be non-negative",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
                stage=-1,
            ),
            "counters cannot be negative",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
                proceeds_quote=Decimal("1"),
                remaining_rebuy_quote=Decimal("2"),
            ),
            "cannot exceed realized proceeds",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
                reference_sell_price=Decimal("0"),
            ),
            "reference prices must be positive",
        ),
        (
            lambda: InventoryRotationState(
                cycle_id="rotation-invalid",
                phase=InventoryRotationPhase.IDLE,
                updated_at=NOW,
                rebuy_band_lower_quote=Decimal("1"),
                rebuy_band_upper_quote=Decimal("1"),
            ),
            "rebuy band is invalid",
        ),
    ],
)
def test_inventory_rotation_state_rejects_invalid_contract_values(
    build_state: Callable[[], InventoryRotationState],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_state()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"fee_ratio": Decimal("-0.1")}, "ratios must be finite and non-negative"),
        ({"maximum_sell_ratio_of_rotation": Decimal("0")}, "sell ratio"),
        ({"maximum_rebuy_ratio_per_stage": Decimal("0")}, "rebuy ratio"),
        ({"minimum_notional_quote": Decimal("0")}, "minimum notional"),
    ],
)
def test_inventory_rotation_policy_rejects_invalid_ratio_and_notional_values(
    kwargs: dict[str, Decimal],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        InventoryRotationPolicy(**kwargs)


def test_inventory_rotation_context_and_proposal_fail_closed_contracts() -> None:
    with pytest.raises(ValueError, match="prices must be finite and positive"):
        InventoryRotationContext(
            price_quote=Decimal("0"),
            resistance_quote=Decimal("1.2"),
            support_quote=Decimal("0.8"),
            sell_trigger_confirmed=False,
            support_reclaimed=False,
        )

    state = InventoryRotationState.new("rotation-proposal", NOW)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        InventoryRotationProposalEngine._hold(state, ()).__class__(
            action=InventoryRotationAction.HOLD,
            proposed_units=Decimal("0"),
            proposed_notional_quote=Decimal("0"),
            estimated_fee_quote=Decimal("0"),
            current_state=state,
            next_state=state,
            blockers=(),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        InventoryRotationProposalEngine._hold(state, ()).__class__(
            action=InventoryRotationAction.SELL,
            proposed_units=Decimal("1"),
            proposed_notional_quote=Decimal("1"),
            estimated_fee_quote=Decimal("0"),
            current_state=state,
            next_state=state,
            blockers=("BLOCKED",),
        )


def test_inventory_rotation_reports_sell_side_inventory_and_notional_blockers() -> None:
    engine = InventoryRotationProposalEngine()
    initial = InventoryRotationState.new("rotation-sell-blockers", NOW)

    no_inventory = engine.review(
        initial,
        InventoryBuckets(
            core_units=Decimal("60"),
            strategic_units=Decimal("0"),
            tactical_units=Decimal("0"),
            cash_quote=Decimal("1000"),
        ),
        InventoryRotationContext(
            price_quote=Decimal("1.20"),
            resistance_quote=Decimal("1.19"),
            support_quote=Decimal("0.90"),
            sell_trigger_confirmed=True,
            support_reclaimed=False,
            average_rotation_cost_quote=Decimal("1.00"),
        ),
    )
    assert "ROTATION_INVENTORY_UNAVAILABLE" in no_inventory.blockers

    below_minimum_notional = engine.review(
        initial,
        InventoryBuckets(
            core_units=Decimal("60"),
            strategic_units=Decimal("20"),
            tactical_units=Decimal("5"),
            cash_quote=Decimal("1000"),
        ),
        InventoryRotationContext(
            price_quote=Decimal("0.50"),
            resistance_quote=Decimal("0.50"),
            support_quote=Decimal("0.30"),
            sell_trigger_confirmed=True,
            support_reclaimed=False,
            average_rotation_cost_quote=Decimal("0.40"),
        ),
    )
    assert below_minimum_notional.action is InventoryRotationAction.BLOCKED
    assert below_minimum_notional.blockers == ("ROTATION_MINIMUM_NOTIONAL_BLOCKED",)


def test_inventory_rotation_reports_rebuy_branch_blockers_and_thresholds() -> None:
    engine = InventoryRotationProposalEngine()
    sell = engine.review(
        InventoryRotationState.new("rotation-rebuy-blockers", NOW),
        _buckets(),
        InventoryRotationContext(
            Decimal("1.2"), Decimal("1.2"), Decimal("0.9"), True, False, Decimal("1")
        ),
    )
    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=sell.proposed_units,
        realized_proceeds_quote=sell.proposed_notional_quote,
        confirmed_at=NOW,
    )

    not_reclaimed = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            Decimal("0.9"), Decimal("1.2"), Decimal("0.9"), False, False
        ),
    )
    assert "INVENTORY_REBUY_RECLAIM_NOT_CONFIRMED" in not_reclaimed.blockers

    above_support_band = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            Decimal("0.95"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
    )
    assert "INVENTORY_REBUY_PRICE_ABOVE_SUPPORT_BAND" in above_support_band.blockers

    missing_band = engine.review(
        InventoryRotationState(
            cycle_id="rotation-missing-band",
            phase=InventoryRotationPhase.AWAITING_REBUY,
            updated_at=NOW,
            proceeds_quote=Decimal("10"),
            remaining_rebuy_quote=Decimal("10"),
            stage=1,
        ),
        _buckets(),
        InventoryRotationContext(
            Decimal("0.9"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
    )
    assert "INVENTORY_REBUY_BAND_UNAVAILABLE" in missing_band.blockers

    above_discount_band = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            Decimal("1.15"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
    )
    assert (
        "INVENTORY_REBUY_PRICE_ABOVE_SELL_DISCOUNT_BAND" in above_discount_band.blockers
    )

    no_cash = engine.review(
        awaiting,
        InventoryBuckets(
            core_units=Decimal("60"),
            strategic_units=Decimal("25"),
            tactical_units=Decimal("15"),
            cash_quote=Decimal("0"),
        ),
        InventoryRotationContext(
            Decimal("0.9"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
    )
    assert "INVENTORY_REBUY_CASH_UNAVAILABLE" in no_cash.blockers

    low_rebuy_notional = engine.review(
        awaiting,
        InventoryBuckets(
            core_units=Decimal("60"),
            strategic_units=Decimal("25"),
            tactical_units=Decimal("15"),
            cash_quote=Decimal("5"),
        ),
        InventoryRotationContext(
            Decimal("0.9"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
        policy=InventoryRotationPolicy(maximum_rebuy_ratio_per_stage=Decimal("1")),
    )
    assert low_rebuy_notional.action is InventoryRotationAction.BLOCKED
    assert low_rebuy_notional.blockers == ("ROTATION_MINIMUM_NOTIONAL_BLOCKED",)


def test_inventory_rotation_confirmation_rejects_invalid_proceeds_and_rebuy_spend() -> (
    None
):
    engine = InventoryRotationProposalEngine()
    sell = engine.review(
        InventoryRotationState.new("rotation-confirm-invalid", NOW),
        _buckets(),
        InventoryRotationContext(
            Decimal("1.2"), Decimal("1.2"), Decimal("0.9"), True, False, Decimal("1")
        ),
    )
    with pytest.raises(ValueError, match="proceeds exceed the proposal"):
        engine.confirm_sell(
            sell.next_state,
            filled_units=sell.proposed_units,
            realized_proceeds_quote=sell.proposed_notional_quote + Decimal("1"),
            confirmed_at=NOW,
        )

    awaiting = engine.confirm_sell(
        sell.next_state,
        filled_units=sell.proposed_units,
        realized_proceeds_quote=sell.proposed_notional_quote,
        confirmed_at=NOW,
    )
    rebuy = engine.review(
        awaiting,
        _buckets(),
        InventoryRotationContext(
            Decimal("0.9"), Decimal("1.2"), Decimal("0.9"), False, True
        ),
        policy=InventoryRotationPolicy(maximum_rebuy_ratio_per_stage=Decimal("1")),
    )
    with pytest.raises(ValueError, match="spend exceeds available proposal cash"):
        engine.confirm_rebuy(
            rebuy.next_state,
            quote_spent=rebuy.proposed_notional_quote + Decimal("1"),
            confirmed_at=NOW,
        )

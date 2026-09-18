"""Deterministic property tests for capital-protection invariants."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai4binance.domain import (
    Action,
    CandidateStatus,
    Decision,
    PriceZone,
    SetupTier,
    Signal,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.events import DeterministicEventBus, DomainEvent
from ai4binance.exchange.filters import (
    LotSizeFilter,
    NotionalFilter,
    PriceFilter,
    SymbolFilters,
)
from ai4binance.execution.trailing import update_long_trailing_stop
from ai4binance.risk import (
    RiskConfig,
    RiskContext,
    RiskEngine,
    VirtualMarketPositionSizingPolicy,
)
from ai4binance.schemas import DataQuality, MarketSnapshot

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)
DECIMAL_SCALE = Decimal("0.000001")
PRICE_TICK = Decimal("0.01")
QUANTITY_STEP = Decimal("0.00000001")
PROPERTY_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    derandomize=True,
    database=None,
)


@PROPERTY_SETTINGS
@given(
    value_units=st.integers(min_value=1, max_value=1_000_000_000),
    step_units=st.integers(min_value=1, max_value=1_000_000),
)
def test_filter_round_down_is_bounded_and_step_aligned(
    value_units: int,
    step_units: int,
) -> None:
    """Rounding never creates quantity/price or violates the selected step."""
    value = Decimal(value_units) * DECIMAL_SCALE
    step = Decimal(step_units) * DECIMAL_SCALE
    price = PriceFilter(Decimal("0"), Decimal("0"), step).round_down(value)
    quantity = LotSizeFilter(Decimal("0"), Decimal("0"), step).round_down(value)

    for rounded in (price, quantity):
        assert Decimal("0") <= rounded <= value
        assert value - rounded < step
        assert rounded % step == Decimal("0")


@PROPERTY_SETTINGS
@given(
    current_ticks=st.integers(min_value=2, max_value=1_000_000),
    previous_seed=st.integers(min_value=0, max_value=1_000_000),
    atr_ticks=st.integers(min_value=1, max_value=2_000_000),
    multiplier_tenths=st.integers(min_value=1, max_value=100),
    tick_units=st.integers(min_value=1, max_value=10_000),
)
def test_long_trailing_stop_is_monotonic_and_tick_aligned(
    current_ticks: int,
    previous_seed: int,
    atr_ticks: int,
    multiplier_tenths: int,
    tick_units: int,
) -> None:
    """A long trailing stop can move up only and always remains below price."""
    tick_size = Decimal(tick_units) * DECIMAL_SCALE
    current_price = Decimal(current_ticks) * tick_size
    previous_ticks = 1 + (previous_seed % (current_ticks - 1))
    previous_stop = Decimal(previous_ticks) * tick_size
    current_atr = Decimal(atr_ticks) * tick_size
    multiplier = Decimal(multiplier_tenths) / Decimal("10")

    update = update_long_trailing_stop(
        previous_stop,
        current_price,
        current_atr,
        multiplier=multiplier,
        tick_size=tick_size,
    )

    assert previous_stop <= update.new_stop < current_price
    assert update.new_stop % tick_size == Decimal("0")
    assert update.moved is (update.new_stop > previous_stop)


@PROPERTY_SETTINGS
@given(
    equity_usdt=st.integers(min_value=10_000, max_value=1_000_000),
    entry_ticks=st.integers(min_value=2, max_value=100_000),
    stop_seed=st.integers(min_value=0, max_value=100_000),
    risk_basis_points=st.integers(min_value=1, max_value=1_000),
    max_trade_usdt=st.integers(min_value=10, max_value=5_000),
    max_open_usdt=st.integers(min_value=10, max_value=5_000),
)
def test_approved_risk_assessment_never_exceeds_capital_limits(
    equity_usdt: int,
    entry_ticks: int,
    stop_seed: int,
    risk_basis_points: int,
    max_trade_usdt: int,
    max_open_usdt: int,
) -> None:
    """Approved sizing remains below risk, trade and exposure caps."""
    entry = Decimal(entry_ticks) * PRICE_TICK
    stop_ticks = 1 + (stop_seed % (entry_ticks - 1))
    stop = entry - (Decimal(stop_ticks) * PRICE_TICK)
    equity = Decimal(equity_usdt)
    risk_ratio = Decimal(risk_basis_points) / Decimal("10000")
    config = RiskConfig(
        max_risk_per_trade=risk_ratio,
        max_trade_usdt=Decimal(max_trade_usdt),
        max_open_position_size_usdt=Decimal(max_open_usdt),
        max_inventory_allocation_ratio=Decimal("1"),
        virtual_market=VirtualMarketPositionSizingPolicy(
            risk_per_trade_ratio=risk_ratio,
            maximum_open_risk_ratio=Decimal("1"),
            maximum_positions=4,
        ),
    )
    assessment = RiskEngine(config).evaluate(
        _approved_candidate(entry, stop),
        _snapshot(entry),
        RiskContext(equity_usdt=equity),
        _permissive_filters(),
    )

    assert assessment.approved is True
    assert assessment.blockers == ()
    assert assessment.risk_amount_usdt <= equity * risk_ratio
    assert assessment.size_usdt <= config.max_open_position_size_usdt
    assert assessment.quantity % QUANTITY_STEP == Decimal("0")


@PROPERTY_SETTINGS
@given(values=st.lists(st.integers(), min_size=2, max_size=30))
def test_event_replay_is_deterministic_and_tamper_evident(
    values: list[int],
) -> None:
    """Canonical event streams replay identically and reject corruption."""
    events = _events(values)
    first_bus = DeterministicEventBus()
    second_bus = DeterministicEventBus()

    first_bus.replay(events)
    second_bus.replay(events)

    assert first_bus.snapshot() == second_bus.snapshot() == events
    with pytest.raises(ValueError, match="duplicate event identity"):
        first_bus.publish(events[-1])
    with pytest.raises(ValueError, match="event sequence is not contiguous"):
        DeterministicEventBus().replay(events[1:])
    with pytest.raises(ValueError, match="event content hash is invalid"):
        replace(events[-1], event_hash="0" * 64)


@PROPERTY_SETTINGS
@given(
    blocker=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=32,
    )
)
def test_signal_blockers_can_never_coexist_with_execution_authority(
    blocker: str,
) -> None:
    """A blocker always prevents an otherwise complete signal from executing."""
    signal = _live_eligible_signal(blocker)

    assert signal.execution_allowed is False
    with pytest.raises(ValueError, match="while blockers exist"):
        replace(signal, execution_allowed=True)


def _approved_candidate(entry: Decimal, stop: Decimal) -> TradeCandidate:
    return TradeCandidate(
        candidate_id="property-risk-candidate",
        snapshot_id="property-risk-snapshot",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        action=Action.BUY,
        setup_name="property_risk_invariant",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(entry, entry),
        invalidation_level=stop,
        stop_loss=stop,
        take_profit_levels=(entry + ((entry - stop) * Decimal("2")),),
        trailing_stop=stop,
        atr=entry - stop,
        risk_reward=Decimal("2"),
        score=80.0,
        confidence=0.8,
        promotion_status=ValidationStatus.PAPER_APPROVED,
        evidence=("PROPERTY_TEST",),
    )


def _snapshot(price: Decimal) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="property-risk-snapshot",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": ()},
        latest_price=price,
        bid=price,
        ask=price,
        spread=Decimal("0"),
        data_quality=DataQuality.DATA_VALID,
    )


def _permissive_filters() -> SymbolFilters:
    return SymbolFilters(
        price=PriceFilter(Decimal("0"), Decimal("0"), PRICE_TICK),
        lot_size=LotSizeFilter(Decimal("0"), Decimal("0"), QUANTITY_STEP),
        notional=NotionalFilter(Decimal("0"), Decimal("0")),
    )


def _events(values: list[int]) -> tuple[DomainEvent, ...]:
    events: list[DomainEvent] = []
    previous_hash = "GENESIS"
    for index, value in enumerate(values, start=1):
        event = DomainEvent.create(
            event_id=f"property-event-{index}",
            aggregate_id="property-aggregate",
            event_type="PROPERTY_OBSERVED",
            sequence=index,
            occurred_at=NOW + timedelta(seconds=index),
            payload=(("value", str(value)),),
            previous_hash=previous_hash,
        )
        events.append(event)
        previous_hash = event.event_hash
    return tuple(events)


def _live_eligible_signal(blocker: str) -> Signal:
    return Signal(
        symbol="HOTUSDT",
        timeframes=("1h",),
        timestamp=NOW,
        snapshot_id="property-signal-snapshot",
        trade_id="property-signal-trade",
        latest_price=Decimal("100"),
        action=Action.BUY,
        decision_state=Decision.BUY,
        setup_name="property_signal_invariant",
        setup_tier=SetupTier.A,
        final_signal_score=80.0,
        confidence=0.8,
        entry_zone=PriceZone(Decimal("100"), Decimal("100")),
        invalidation_level=Decimal("95"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        trailing_stop=Decimal("95"),
        atr=Decimal("3"),
        risk_reward=Decimal("2"),
        size_usdt=Decimal("100"),
        reason_codes=("PROPERTY_TEST",),
        reason_summary="Property test signal.",
        blockers=(blocker,),
        validation_status=ValidationStatus.LIVE_ELIGIBLE,
    )

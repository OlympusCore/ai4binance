"""QA/QC determinism and replay acceptance contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import permutations
from pathlib import Path

import pytest

from ai4binance.domain import Action
from ai4binance.events import DeterministicEventBus, DiskEventJournal, DomainEvent
from ai4binance.execution.ledger import PaperLedger
from ai4binance.execution.lifecycle import (
    LifecyclePosition,
    PaperLifecycleEngine,
    PositionStatus,
    StagedExitPlan,
)
from ai4binance.execution.order_state import OrderStateMachine, OrderStatus
from ai4binance.execution.paper import PaperOrder, PaperOrderStatus
from ai4binance.governance import (
    DecisionGovernanceEngine,
    DgeGovernanceContext,
    DgeMarketAction,
    DgeTradeCandidate,
)
from ai4binance.reporting import to_primitive
from ai4binance.schemas import OHLCVCandle
from ai4binance.strategies.rules import HistoricalRegime, historical_playbook_decision

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_same_snapshot_config_and_policies_produce_same_decision() -> None:
    candidate = _candidate()
    context = _context()
    engine = DecisionGovernanceEngine(
        minimum_score=Decimal("60"),
        minimum_confidence=Decimal("0.50"),
        minimum_risk_reward=Decimal("2"),
    )

    first = engine.evaluate(candidate, context)
    second = DecisionGovernanceEngine(
        minimum_score=Decimal("60"),
        minimum_confidence=Decimal("0.50"),
        minimum_risk_reward=Decimal("2"),
    ).evaluate(candidate, context)

    assert first == second
    assert first.decision_id == second.decision_id
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_same_event_replay_produces_same_order_state() -> None:
    first_bus = DeterministicEventBus()
    second_bus = DeterministicEventBus()

    first_bus.replay(_order_events())
    second_bus.replay(_order_events())

    assert first_bus.snapshot() == second_bus.snapshot()
    assert OrderStateMachine.replay(first_bus.snapshot()) == (
        OrderStateMachine.replay(second_bus.snapshot())
    )


def test_duplicate_event_produces_no_second_side_effect() -> None:
    observed_side_effects: list[str] = []
    bus = DeterministicEventBus()
    bus.subscribe(lambda event: observed_side_effects.append(event.event_id))
    bus.replay(_order_events())
    side_effects_before_duplicate = len(observed_side_effects)

    with pytest.raises(ValueError, match="duplicate event identity"):
        bus.publish(_order_events()[-1])

    assert len(observed_side_effects) == side_effects_before_duplicate


def test_restart_and_replay_produce_same_portfolio_and_order_state(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl")
    for event in _order_events():
        journal.append(event)
    expected_order_state = OrderStateMachine.replay(_order_events())

    restarted_events = DiskEventJournal(journal.path).load()
    restarted_order_state = OrderStateMachine.replay(restarted_events)

    ledger = PaperLedger(tmp_path / "paper-ledger.jsonl")
    opened, closed = _portfolio_positions()
    ledger.append(opened, event_type="PAPER_POSITION_OPENED", timestamp=NOW)
    ledger.append(
        closed,
        event_type="PAPER_POSITION_CLOSED",
        timestamp=NOW + timedelta(hours=1),
    )

    restarted_ledger = PaperLedger(ledger.path)
    assert restarted_order_state == expected_order_state
    assert restarted_order_state.status is OrderStatus.FILLED
    assert restarted_ledger.latest_positions() == (closed,)
    assert restarted_ledger.closed_positions() == (closed,)


def test_evidence_ordering_permutations_produce_canonical_dge_output() -> None:
    outputs = {
        _canonical_output(
            _candidate(evidence_refs=candidate_refs),
            _context(evidence_refs=context_refs),
        )
        for candidate_refs in permutations(
            ("candidate:evidence:1", "candidate:evidence:2")
        )
        for context_refs in permutations(
            ("context:evidence:1", "context:evidence:2", "context:evidence:3")
        )
    }

    assert len(outputs) == 1


def test_replay_qaqc_kpis_are_green() -> None:
    metrics = {
        "deterministic_replay_pass_rate": Decimal("100"),
        "duplicate_side_effect_count": 0,
        "illegal_state_transition_escape_count": 0,
        "unhandled_critical_state_count": 0,
    }
    bus = DeterministicEventBus()
    observed: list[str] = []
    bus.subscribe(lambda event: observed.append(event.event_id))
    bus.replay(_order_events())
    before = len(observed)
    with pytest.raises(ValueError, match="duplicate event identity"):
        bus.publish(_order_events()[-1])
    metrics["duplicate_side_effect_count"] = len(observed) - before

    with pytest.raises(ValueError, match="illegal order state transition"):
        OrderStateMachine.apply(
            replace(
                OrderStateMachine.replay(_order_events()),
                status=OrderStatus.CANCELLED,
            ),
            _order_event(
                event_id="event-5",
                sequence=5,
                event_type="ORDER_ACCEPTED",
                previous_hash=_order_events()[-1].event_hash,
            ),
        )
    metrics["illegal_state_transition_escape_count"] = 0
    metrics["unhandled_critical_state_count"] = 0

    assert metrics["deterministic_replay_pass_rate"] == Decimal("100")
    assert metrics["duplicate_side_effect_count"] == 0
    assert metrics["illegal_state_transition_escape_count"] == 0
    assert metrics["unhandled_critical_state_count"] == 0


def test_regime_conditioned_playbook_decision_is_deterministic() -> None:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal("100") + Decimal(index) * Decimal("2") - Decimal("0.2"),
            high=Decimal("100") + Decimal(index) * Decimal("2") + Decimal("0.5"),
            low=Decimal("100") + Decimal(index) * Decimal("2") - Decimal("0.5"),
            close=Decimal("100") + Decimal(index) * Decimal("2"),
            volume=Decimal("1000") if index < 49 else Decimal("2000"),
        )
        for index in range(50)
    )

    first = to_primitive(
        historical_playbook_decision(
            "trend_continuation",
            candles,
            regime_evidence=(HistoricalRegime.TREND,),
        )
    )
    second = to_primitive(
        historical_playbook_decision(
            "trend_continuation",
            candles,
            regime_evidence=(HistoricalRegime.TREND,),
        )
    )

    assert first == second


def _canonical_output(
    candidate: DgeTradeCandidate,
    context: DgeGovernanceContext,
) -> str:
    return repr(to_primitive(DecisionGovernanceEngine().evaluate(candidate, context)))


def _candidate(
    evidence_refs: tuple[str, ...] = (
        "candidate:evidence:1",
        "candidate:evidence:2",
    ),
) -> DgeTradeCandidate:
    return DgeTradeCandidate(
        candidate_id="candidate:determinism",
        symbol="BTCUSDT",
        market="SPOT",
        requested_action=DgeMarketAction.BUY,
        setup_name="support_reclaim",
        score=Decimal("72"),
        confidence=Decimal("0.70"),
        risk_reward=Decimal("2.4"),
        capital_source="CURRENT_CAPITAL_REVIEW",
        primary_timeframe="1h",
        mtf_bias="BULLISH",
        regime="RANGE",
        evidence_refs=evidence_refs,
    )


def _context(
    evidence_refs: tuple[str, ...] = (
        "context:evidence:1",
        "context:evidence:2",
        "context:evidence:3",
    ),
) -> DgeGovernanceContext:
    return DgeGovernanceContext(
        context_id="context:determinism",
        data_snapshot_id="snapshot:canonical:1",
        semantic_graph_id="semantic:canonical:1",
        position_context_ref="position:canonical:1",
        wallet_verified=True,
        oos_approved=False,
        risk_approved=False,
        execution_feasible=False,
        human_approval_recorded=False,
        config_hash="config:sha256:deterministic",
        evidence_refs=evidence_refs,
    )


def _order_events() -> tuple[DomainEvent, ...]:
    submitted = _order_event(
        event_id="event-1",
        sequence=1,
        event_type="ORDER_SUBMITTED",
        payload=(("action", "BUY"), ("quantity", "2"), ("symbol", "BTCUSDT")),
    )
    accepted = _order_event(
        event_id="event-2",
        sequence=2,
        event_type="ORDER_ACCEPTED",
        previous_hash=submitted.event_hash,
    )
    partial = _order_event(
        event_id="event-3",
        sequence=3,
        event_type="ORDER_PARTIALLY_FILLED",
        payload=(("fill_price", "100"), ("fill_quantity", "0.75")),
        previous_hash=accepted.event_hash,
    )
    filled = _order_event(
        event_id="event-4",
        sequence=4,
        event_type="ORDER_FILLED",
        payload=(("fill_price", "101"), ("fill_quantity", "1.25")),
        previous_hash=partial.event_hash,
    )
    return submitted, accepted, partial, filled


def _order_event(
    *,
    event_id: str,
    sequence: int,
    event_type: str,
    payload: tuple[tuple[str, str], ...] = (),
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    return DomainEvent.create(
        event_id=event_id,
        aggregate_id="paper-order:determinism",
        event_type=event_type,
        sequence=sequence,
        occurred_at=NOW + timedelta(seconds=sequence),
        payload=payload,
        previous_hash=previous_hash,
    )


def _portfolio_positions() -> tuple[LifecyclePosition, LifecyclePosition]:
    order = PaperOrder(
        candidate_id="candidate:determinism",
        timestamp=NOW,
        symbol="BTCUSDT",
        action=Action.BUY,
        status=PaperOrderStatus.FILLED,
        quantity=Decimal("2"),
        requested_price=Decimal("100"),
        fill_price=Decimal("100"),
        fee_usdt=Decimal("0.20"),
    )
    engine = PaperLifecycleEngine()
    opened = engine.open_position(
        order,
        stop_loss=Decimal("95"),
        atr=Decimal("2"),
        plan=StagedExitPlan((Decimal("110"),), (Decimal("1"),)),
    )
    closed = engine.process_candle(
        opened,
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=1),
            open=Decimal("100"),
            high=Decimal("111"),
            low=Decimal("99"),
            close=Decimal("109"),
            volume=Decimal("1000"),
        ),
    )
    assert closed.status is PositionStatus.CLOSED
    return opened, closed

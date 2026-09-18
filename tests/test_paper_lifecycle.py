"""Persistent staged paper lifecycle and closure-review tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.domain import Action
from ai4binance.execution.ledger import PaperLedger
from ai4binance.execution.lifecycle import (
    ClosureContext,
    LifecycleExit,
    LifecyclePosition,
    PaperLifecycleEngine,
    PositionStatus,
    StagedExitPlan,
)
from ai4binance.execution.paper import ExitReason, PaperOrder, PaperOrderStatus
from ai4binance.execution.trailing import DEFAULT_TRAILING_MULTIPLIER
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 3, 1, tzinfo=UTC)


def filled_order() -> PaperOrder:
    return PaperOrder(
        candidate_id="candidate-1",
        timestamp=NOW,
        symbol="HOTUSDT",
        action=Action.BUY,
        status=PaperOrderStatus.FILLED,
        quantity=Decimal("2"),
        requested_price=Decimal("100"),
        fill_price=Decimal("100"),
        fee_usdt=Decimal("0.2"),
    )


def plan() -> StagedExitPlan:
    return StagedExitPlan(
        targets=(Decimal("110"), Decimal("120")),
        quantity_ratios=(Decimal("0.5"), Decimal("0.5")),
    )


def candle(
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


def open_position() -> LifecyclePosition:
    return PaperLifecycleEngine().open_position(
        filled_order(),
        stop_loss=Decimal("95"),
        atr=Decimal("2"),
        plan=plan(),
    )


def test_staged_targets_partially_then_fully_close_position() -> None:
    engine = PaperLifecycleEngine()
    position = open_position()

    partial = engine.process_candle(position, candle(1, "100", "111", "99", "108"))
    closed = engine.process_candle(
        partial,
        candle(2, "108", "121", "106", "118"),
        ClosureContext(ignored_signals=2, htf_weakness=True),
    )

    assert partial.status is PositionStatus.PARTIALLY_CLOSED
    assert partial.remaining_quantity == Decimal("1.0")
    assert partial.next_target_index == 1
    assert partial.trailing_stop == Decimal("105.0")
    assert closed.status is PositionStatus.CLOSED
    assert closed.remaining_quantity == Decimal("0.0")
    assert len(closed.exits) == 2
    assert closed.closure_review is not None
    assert closed.closure_review.exit_reason is ExitReason.TAKE_PROFIT_EXIT
    assert closed.closure_review.ignored_signals == 2
    assert closed.closure_review.htf_weakness is True
    assert closed.closure_review.staged_exit_alternative == "USED"
    assert closed.realized_pnl_usdt > Decimal("29")


def test_stop_first_prevents_optimistic_same_bar_staged_exit() -> None:
    closed = PaperLifecycleEngine().process_candle(
        open_position(),
        candle(1, "100", "121", "94", "110"),
    )

    assert closed.status is PositionStatus.CLOSED
    assert len(closed.exits) == 1
    assert closed.exits[0].reason is ExitReason.STOP_LOSS_EXIT
    assert closed.exits[0].quantity == Decimal("2")
    assert closed.realized_pnl_usdt < Decimal("-10")


def test_trailing_exit_records_context_and_never_same_bar_triggers() -> None:
    engine = PaperLifecycleEngine(tick_size=Decimal("0.1"))
    assert PaperLifecycleEngine().trailing_multiplier == DEFAULT_TRAILING_MULTIPLIER
    moved = engine.process_candle(
        open_position(),
        candle(1, "100", "109", "98", "105"),
    )
    closed = engine.process_candle(
        moved,
        candle(2, "104", "106", "101", "103"),
        ClosureContext(volatility_expansion=True, level_break=True),
    )

    assert moved.status is PositionStatus.OPEN
    assert moved.trailing_stop == Decimal("102.0")
    assert closed.exits[0].reason is ExitReason.TRAILING_STOP_EXIT
    assert closed.exits[0].price == Decimal("101.94900")
    assert closed.closure_review is not None
    assert closed.closure_review.trailing_quality == "PROTECTIVE"
    assert closed.closure_review.volatility_expansion is True
    assert closed.closure_review.level_break is True
    assert closed.closure_review.ignored_structure_break is True


def test_trailing_updates_after_all_partial_targets_are_exhausted() -> None:
    engine = PaperLifecycleEngine(tick_size=Decimal("0.1"))
    partial_plan = StagedExitPlan(
        targets=(Decimal("110"), Decimal("120")),
        quantity_ratios=(Decimal("0.25"), Decimal("0.25")),
    )
    position = engine.open_position(
        filled_order(),
        stop_loss=Decimal("95"),
        atr=Decimal("2"),
        plan=partial_plan,
    )

    updated = engine.process_candle(position, candle(1, "100", "121", "99", "118"))

    assert updated.status is PositionStatus.PARTIALLY_CLOSED
    assert updated.next_target_index == 2
    assert updated.remaining_quantity == Decimal("1.00")
    assert updated.trailing_stop == Decimal("115.0")


def test_ledger_persists_and_reconstructs_latest_position_payload(
    tmp_path: Path,
) -> None:
    engine = PaperLifecycleEngine()
    opened = open_position()
    partial = engine.process_candle(opened, candle(1, "100", "111", "99", "108"))
    closed = engine.process_candle(partial, candle(2, "108", "121", "106", "118"))
    ledger = PaperLedger(tmp_path / "paper-ledger.jsonl")

    ledger.append(opened, event_type="PAPER_POSITION_OPENED", timestamp=NOW)
    ledger.append(
        partial,
        event_type="PAPER_POSITION_PARTIALLY_CLOSED",
        timestamp=NOW + timedelta(hours=1),
    )
    ledger.append(
        closed,
        event_type="PAPER_POSITION_CLOSED",
        timestamp=NOW + timedelta(hours=2),
    )

    latest = ledger.latest_payload(opened.position_id)
    reconstructed = ledger.latest_position(opened.position_id)
    assert latest is not None
    assert latest["status"] == "CLOSED"
    assert latest["remaining_quantity"] == "0.0"
    assert reconstructed == closed
    assert ledger.latest_positions() == (closed,)
    assert ledger.closed_positions() == (closed,)
    assert ledger.latest_payload("missing") is None
    assert ledger.latest_position("missing") is None


def test_lifecycle_rejects_invalid_transitions_and_plans(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="aligned"):
        StagedExitPlan((Decimal("110"),), (Decimal("0.5"), Decimal("0.5")))
    with pytest.raises(ValueError, match="positive"):
        StagedExitPlan((Decimal("0"),), (Decimal("0.5"),))
    with pytest.raises(ValueError, match="ascending"):
        StagedExitPlan(
            (Decimal("110"), Decimal("110")),
            (Decimal("0.5"), Decimal("0.5")),
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        StagedExitPlan((Decimal("110"),), (Decimal("1.1"),))
    rejected = replace(
        filled_order(),
        status=PaperOrderStatus.REJECTED,
        blockers=("BLOCKED",),
    )
    with pytest.raises(ValueError, match="only filled"):
        PaperLifecycleEngine().open_position(
            rejected,
            stop_loss=Decimal("95"),
            atr=Decimal("2"),
            plan=plan(),
        )
    with pytest.raises(ValueError, match="Spot BUY"):
        PaperLifecycleEngine().open_position(
            replace(filled_order(), action=Action.SELL),
            stop_loss=Decimal("95"),
            atr=Decimal("2"),
            plan=plan(),
        )
    with pytest.raises(ValueError, match="below entry"):
        PaperLifecycleEngine().open_position(
            filled_order(),
            stop_loss=Decimal("100"),
            atr=Decimal("2"),
            plan=plan(),
        )
    with pytest.raises(ValueError, match="above entry"):
        PaperLifecycleEngine().open_position(
            filled_order(),
            stop_loss=Decimal("95"),
            atr=Decimal("2"),
            plan=StagedExitPlan((Decimal("100"),), (Decimal("1"),)),
        )
    closed = PaperLifecycleEngine().process_candle(
        open_position(),
        candle(1, "100", "101", "94", "96"),
    )
    with pytest.raises(ValueError, match="closed paper position"):
        PaperLifecycleEngine().process_candle(
            closed,
            candle(2, "96", "97", "95", "96"),
        )
    with pytest.raises(ValueError, match="cannot precede"):
        PaperLifecycleEngine().process_candle(
            open_position(),
            candle(-1, "100", "101", "99", "100"),
        )
    with pytest.raises(ValueError, match="ignored signal"):
        ClosureContext(ignored_signals=-1)
    assert PaperLedger(tmp_path / "missing.jsonl").latest_payload("x") is None


def test_lifecycle_value_objects_reject_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LifecycleExit(
            datetime(2026, 3, 1),
            ExitReason.STOP_LOSS_EXIT,
            Decimal("95"),
            Decimal("1"),
            Decimal("0.1"),
            Decimal("-5"),
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        LifecycleExit(
            NOW,
            ExitReason.STOP_LOSS_EXIT,
            Decimal("-1"),
            Decimal("1"),
            Decimal("0.1"),
            Decimal("-5"),
        )
    with pytest.raises(ValueError, match="identity"):
        replace(open_position(), position_id=" ")
    with pytest.raises(ValueError, match="symbol"):
        replace(open_position(), symbol=" ")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(open_position(), opened_at=datetime(2026, 3, 1))
    with pytest.raises(ValueError, match="positive except zero fee"):
        replace(open_position(), entry_price=Decimal("0"))
    with pytest.raises(ValueError, match="remaining quantity"):
        replace(open_position(), remaining_quantity=Decimal("3"))
    with pytest.raises(ValueError, match="closed position"):
        replace(open_position(), status=PositionStatus.CLOSED)
    with pytest.raises(ValueError, match="active position"):
        replace(open_position(), remaining_quantity=Decimal("0"))


def test_lifecycle_configuration_rejects_unsafe_costs() -> None:
    with pytest.raises(ValueError, match="fee_ratio"):
        PaperLifecycleEngine(fee_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="slippage_ratio"):
        PaperLifecycleEngine(slippage_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="must be positive"):
        PaperLifecycleEngine(tick_size=Decimal("0"))

"""Paper-only execution and trailing lifecycle tests."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationStatus,
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.execution.paper import (
    ExitReason,
    PaperBroker,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
)
from ai4binance.execution.trailing import update_long_trailing_stop
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.risk import RiskAssessment
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def approved_assessment() -> RiskAssessment:
    return RiskAssessment(
        candidate_id="candidate-1",
        approved=True,
        size_usdt=Decimal("100"),
        quantity=Decimal("1"),
        risk_amount_usdt=Decimal("5"),
    )


def approved_candidate() -> TradeCandidate:
    return TradeCandidate(
        candidate_id="candidate-1",
        snapshot_id="snapshot-1",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        action=Action.BUY,
        setup_name="trend_continuation",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(Decimal("100"), Decimal("100")),
        invalidation_level=Decimal("95"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        trailing_stop=Decimal("95"),
        atr=Decimal("3.33"),
        risk_reward=Decimal("2"),
        score=80,
        confidence=0.8,
        promotion_status=ValidationStatus.PAPER_APPROVED,
    )


def test_paper_broker_fills_promoted_risk_approved_candidate() -> None:
    order = PaperBroker().submit(approved_candidate(), approved_assessment(), NOW)
    assert order.status is PaperOrderStatus.FILLED
    assert order.fill_price == Decimal("100.0500")
    assert order.fee_usdt == Decimal("0.1000500")


def test_paper_broker_rejects_research_candidate() -> None:
    candidate = replace(
        approved_candidate(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    order = PaperBroker().submit(candidate, approved_assessment(), NOW)
    assert order.status is PaperOrderStatus.REJECTED
    assert "SIMULATION_PROMOTION_REQUIRED" in order.blockers


def test_paper_broker_accepts_virtual_eligibility_without_paper_promotion() -> None:
    candidate = replace(
        approved_candidate(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    eligibility = evaluate_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
    )

    order = PaperBroker().submit(
        candidate,
        approved_assessment(),
        NOW,
        virtual_eligibility=eligibility,
    )

    assert eligibility.status is VirtualSimulationStatus.ELIGIBLE
    assert order.status is PaperOrderStatus.FILLED


def test_paper_broker_rejects_auto_submit_for_binance_market_surface() -> None:
    order = PaperBroker(execution_surface=ExecutionSurface.BINANCE_MARKET).submit(
        approved_candidate(),
        approved_assessment(),
        NOW,
    )

    assert order.status is PaperOrderStatus.REJECTED
    assert "HUMAN_HAND_MANUAL_EXECUTION_REQUIRED" in order.blockers
    assert "AUTO_SIMULATION_NOT_ALLOWED" in order.blockers


def test_paper_broker_rejects_risk_veto_for_promoted_candidate() -> None:
    assessment = RiskAssessment(
        candidate_id="candidate-1",
        approved=False,
        size_usdt=Decimal("100"),
        quantity=Decimal("1"),
        risk_amount_usdt=Decimal("5"),
        blockers=("RISK.VETO",),
    )

    order = PaperBroker().submit(approved_candidate(), assessment, NOW)

    assert order.status is PaperOrderStatus.REJECTED
    assert order.blockers == ("RISK.VETO", "RISK_NOT_APPROVED")
    assert order.fill_price == Decimal("0")


def test_paper_broker_rejects_candidate_not_ready_for_risk() -> None:
    candidate = replace(
        approved_candidate(),
        status=CandidateStatus.RESEARCH_ONLY,
    )

    order = PaperBroker().submit(candidate, approved_assessment(), NOW)

    assert order.status is PaperOrderStatus.REJECTED
    assert "CANDIDATE_NOT_READY" in order.blockers


def test_paper_broker_applies_sell_side_slippage_for_inventory_exit() -> None:
    candidate = replace(
        approved_candidate(),
        action=Action.SELL,
        invalidation_level=Decimal("105"),
        stop_loss=Decimal("105"),
        take_profit_levels=(Decimal("90"),),
        trailing_stop=Decimal("105"),
        inventory_action="REDUCE",
    )

    order = PaperBroker().submit(candidate, approved_assessment(), NOW)

    assert order.status is PaperOrderStatus.FILLED
    assert order.fill_price == Decimal("99.9500")
    assert order.fee_usdt == Decimal("0.0999500")


def test_approved_risk_assessment_requires_positive_sizing() -> None:
    with pytest.raises(ValueError, match="values must be positive"):
        RiskAssessment(candidate_id="candidate-1", approved=True)


def test_paper_broker_defensively_rejects_zero_quantity() -> None:
    assessment = RiskAssessment(
        candidate_id="candidate-1",
        approved=False,
        blockers=("UPSTREAM_BLOCKER",),
    )
    order = PaperBroker().submit(approved_candidate(), assessment, NOW)
    assert order.status is PaperOrderStatus.REJECTED
    assert "INVALID_PAPER_QUANTITY" in order.blockers


def test_long_trailing_stop_moves_up_only_and_rounds_to_tick() -> None:
    moved = update_long_trailing_stop(
        Decimal("95"),
        Decimal("105"),
        Decimal("2"),
        tick_size=Decimal("0.1"),
    )
    assert moved.new_stop == Decimal("102.0")
    assert moved.moved is True
    unchanged = update_long_trailing_stop(
        moved.new_stop,
        Decimal("104"),
        Decimal("2"),
        tick_size=Decimal("0.1"),
    )
    assert unchanged.new_stop == Decimal("102.0")
    assert unchanged.moved is False


def test_paper_lifecycle_uses_pessimistic_stop_first_ordering() -> None:
    position = PaperPosition(
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("97"),
        take_profit_levels=(Decimal("110"),),
    )
    both_hit = OHLCVCandle(
        NOW,
        Decimal("100"),
        Decimal("111"),
        Decimal("96"),
        Decimal("105"),
        Decimal("100"),
    )
    exit_event = PaperBroker.evaluate_long_exit(position, both_hit)
    assert exit_event is not None
    assert exit_event.reason is ExitReason.TRAILING_STOP_EXIT
    assert exit_event.price == Decimal("97")


def test_profitable_trailing_stop_is_valid_and_gap_fill_is_conservative() -> None:
    position = PaperPosition(
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("105"),
        take_profit_levels=(Decimal("120"),),
    )
    gap_down = OHLCVCandle(
        NOW,
        Decimal("103"),
        Decimal("104"),
        Decimal("101"),
        Decimal("102"),
        Decimal("100"),
    )

    exit_event = PaperBroker.evaluate_long_exit(position, gap_down)

    assert exit_event is not None
    assert exit_event.reason is ExitReason.TRAILING_STOP_EXIT
    assert exit_event.price == Decimal("103")


def test_long_exit_reports_stop_loss_take_profit_and_no_exit() -> None:
    position = PaperPosition(
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
    )
    stop_loss = OHLCVCandle(
        NOW,
        Decimal("96"),
        Decimal("100"),
        Decimal("94"),
        Decimal("99"),
        Decimal("100"),
    )
    take_profit = OHLCVCandle(
        NOW,
        Decimal("100"),
        Decimal("111"),
        Decimal("96"),
        Decimal("109"),
        Decimal("100"),
    )
    no_exit = OHLCVCandle(
        NOW,
        Decimal("100"),
        Decimal("109"),
        Decimal("96"),
        Decimal("105"),
        Decimal("100"),
    )

    stop_exit = PaperBroker.evaluate_long_exit(position, stop_loss)
    profit_exit = PaperBroker.evaluate_long_exit(position, take_profit)

    assert stop_exit is not None
    assert stop_exit.reason is ExitReason.STOP_LOSS_EXIT
    assert stop_exit.price == Decimal("95")
    assert profit_exit is not None
    assert profit_exit.reason is ExitReason.TAKE_PROFIT_EXIT
    assert profit_exit.price == Decimal("110")
    assert PaperBroker.evaluate_long_exit(position, no_exit) is None


def test_trailing_and_paper_configuration_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        update_long_trailing_stop(
            Decimal("0"),
            Decimal("100"),
            Decimal("2"),
            tick_size=Decimal("0.1"),
        )
    with pytest.raises(ValueError, match="fee_ratio"):
        PaperBroker(fee_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="slippage_ratio"):
        PaperBroker(slippage_ratio=Decimal("0.1"))


def test_paper_order_rejects_invalid_timestamp_numbers_and_filled_blockers() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PaperOrder(
            candidate_id="candidate-1",
            timestamp=datetime(2026, 7, 11),
            symbol="HOTUSDT",
            action=Action.BUY,
            status=PaperOrderStatus.REJECTED,
            quantity=Decimal("1"),
            requested_price=Decimal("100"),
            fill_price=Decimal("0"),
            fee_usdt=Decimal("0"),
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        PaperOrder(
            candidate_id="candidate-1",
            timestamp=NOW,
            symbol="HOTUSDT",
            action=Action.BUY,
            status=PaperOrderStatus.REJECTED,
            quantity=Decimal("-1"),
            requested_price=Decimal("100"),
            fill_price=Decimal("0"),
            fee_usdt=Decimal("0"),
        )
    with pytest.raises(ValueError, match="filled paper order"):
        PaperOrder(
            candidate_id="candidate-1",
            timestamp=NOW,
            symbol="HOTUSDT",
            action=Action.BUY,
            status=PaperOrderStatus.FILLED,
            quantity=Decimal("1"),
            requested_price=Decimal("100"),
            fill_price=Decimal("100"),
            fee_usdt=Decimal("0.1"),
            blockers=("UNEXPECTED_BLOCKER",),
        )


def test_paper_position_rejects_invalid_values_stop_and_targets() -> None:
    with pytest.raises(ValueError, match="values must be positive"):
        PaperPosition(
            candidate_id="candidate-1",
            symbol="HOTUSDT",
            entry_price=Decimal("100"),
            quantity=Decimal("0"),
            stop_loss=Decimal("95"),
            trailing_stop=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
        )
    with pytest.raises(ValueError, match="below entry"):
        PaperPosition(
            candidate_id="candidate-1",
            symbol="HOTUSDT",
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            stop_loss=Decimal("100"),
            trailing_stop=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
        )
    with pytest.raises(ValueError, match="above entry"):
        PaperPosition(
            candidate_id="candidate-1",
            symbol="HOTUSDT",
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            stop_loss=Decimal("95"),
            trailing_stop=Decimal("95"),
            take_profit_levels=(Decimal("100"),),
        )

"""Paper-only execution and trailing lifecycle tests."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

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
    PaperOrderStatus,
    PaperPosition,
)
from ai4binance.execution.trailing import update_long_trailing_stop
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
    assert "PAPER_PROMOTION_REQUIRED" in order.blockers


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

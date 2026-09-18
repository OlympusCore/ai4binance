"""Domain contract tests."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai4binance.domain import (
    FIRST_SETUP_QUALITY_QUESTION,
    Action,
    AgentScore,
    CandidateStatus,
    Decision,
    PriceZone,
    SetupScanDisposition,
    SetupTier,
    Signal,
    SignalSubScores,
    TradeCandidate,
    ValidationStatus,
    setup_scan_disposition,
)


def test_signal_defaults_to_no_trade() -> None:
    signal = Signal(symbol="hotusdt", timeframes=("1h",))
    assert signal.symbol == "HOTUSDT"
    assert signal.action is Action.NO_TRADE
    assert signal.decision_state is Decision.NO_TRADE
    assert signal.setup_tier is SetupTier.NO_TRADE
    assert signal.sub_scores.risk_penalty_score == 0.0
    assert signal.take_profit_levels == ()
    assert signal.execution_allowed is False


@pytest.mark.parametrize("invalid_score", [-0.1, 100.1, float("nan")])
def test_signal_rejects_invalid_score(invalid_score: float) -> None:
    with pytest.raises(ValueError, match="finite and between 0 and 100"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            final_signal_score=invalid_score,
        )


def test_sub_scores_reject_invalid_score_family_value() -> None:
    with pytest.raises(ValueError, match="trend_score"):
        SignalSubScores(trend_score=-0.01)


def test_signal_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            timestamp=datetime(2026, 1, 1),
        )


def test_signal_rejects_contradictory_action_and_decision() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            action=Action.BUY,
            decision_state=Decision.SELL,
            inventory_action="REDUCE",
        )


def test_signal_rejects_tier_without_score_evidence() -> None:
    with pytest.raises(ValueError, match="setup_tier exceeds"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            setup_tier=SetupTier.A,
            final_signal_score=77.99,
        )


def test_setup_quality_uses_why_not_to_trade_scan_contract() -> None:
    assert FIRST_SETUP_QUALITY_QUESTION == "WHY_NOT_TO_TRADE"
    assert setup_scan_disposition(SetupTier.A_STAR) is SetupScanDisposition.DISPLAY
    assert setup_scan_disposition(SetupTier.A) is SetupScanDisposition.DISPLAY
    assert setup_scan_disposition(SetupTier.B_PLUS) is SetupScanDisposition.DISPLAY
    assert setup_scan_disposition(SetupTier.B) is SetupScanDisposition.WATCH_ONLY
    assert setup_scan_disposition(SetupTier.C) is SetupScanDisposition.WATCH_ONLY
    assert setup_scan_disposition(SetupTier.NO_TRADE) is SetupScanDisposition.WATCH_ONLY


def test_wait_action_is_distinct_from_hold_and_no_trade() -> None:
    signal = Signal(
        symbol="HOTUSDT",
        timeframes=("1h",),
        action=Action.WAIT,
        decision_state=Decision.WAIT,
        setup_tier=SetupTier.B_PLUS,
        final_signal_score=76.0,
        execution_allowed=False,
    )

    assert signal.action is Action.WAIT
    assert signal.action.value == "WAIT"
    assert signal.decision_state is Decision.WAIT


def test_spot_sell_requires_inventory_action() -> None:
    with pytest.raises(ValueError, match="inventory_action"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            action=Action.SELL,
            decision_state=Decision.SELL,
        )


def test_signal_futures_sell_allows_missing_inventory_action() -> None:
    signal = Signal(
        symbol="HOTUSDT",
        timeframes=("1h",),
        action=Action.SELL,
        decision_state=Decision.SELL,
        market_type="USD_M_FUTURES",
        reason_codes=("FUTURES_SELL",),
        reason_summary="Futures decisions may sell without an inventory action.",
    )

    assert signal.market_type == "USD_M_FUTURES"
    assert signal.action is Action.SELL


def test_signal_rejects_unsupported_market_type() -> None:
    with pytest.raises(ValueError, match="market_type must be SPOT or USD_M_FUTURES"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            market_type="OPTIONS",
        )


def test_futures_sell_allows_missing_inventory_action() -> None:
    candidate = TradeCandidate(
        candidate_id="candidate-1",
        snapshot_id="snapshot-1",
        timestamp=datetime(2026, 7, 11, tzinfo=UTC),
        symbol="HOTUSDT",
        timeframe="1h",
        action=Action.SELL,
        setup_name="trend_continuation",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(Decimal("100"), Decimal("100")),
        invalidation_level=Decimal("105"),
        stop_loss=Decimal("105"),
        take_profit_levels=(Decimal("95"),),
        trailing_stop=Decimal("105"),
        atr=Decimal("3"),
        risk_reward=Decimal("2"),
        score=80,
        confidence=0.8,
        market_type="USD_M_FUTURES",
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )

    assert candidate.market_type == "USD_M_FUTURES"
    assert candidate.action is Action.SELL


def test_trade_candidate_defaults_to_canonical_spot_market_type() -> None:
    candidate = TradeCandidate(
        candidate_id="candidate-spot-default",
        snapshot_id="snapshot-1",
        timestamp=datetime(2026, 7, 11, tzinfo=UTC),
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
        atr=Decimal("3"),
        risk_reward=Decimal("2"),
        score=80,
        confidence=0.8,
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )

    assert candidate.market_type == "SPOT"


def test_executable_signal_requires_complete_risk_context() -> None:
    with pytest.raises(ValueError, match="execution context is incomplete"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            action=Action.BUY,
            decision_state=Decision.BUY,
            setup_tier=SetupTier.A,
            final_signal_score=80.0,
            validation_status=ValidationStatus.LIVE_ELIGIBLE,
            execution_allowed=True,
        )


def test_executable_signal_accepts_complete_validated_context() -> None:
    signal = Signal(
        symbol="HOTUSDT",
        timeframes=("5m", "15m", "1h", "4h", "1d"),
        timestamp=datetime(2026, 7, 11, tzinfo=UTC),
        snapshot_id="snapshot-1",
        trade_id="trade-1",
        latest_price=Decimal("0.001"),
        action=Action.BUY,
        decision_state=Decision.BUY,
        setup_tier=SetupTier.A,
        final_signal_score=80.0,
        confidence=0.8,
        entry_zone=PriceZone(Decimal("0.00099"), Decimal("0.001")),
        invalidation_level=Decimal("0.00089"),
        stop_loss=Decimal("0.0009"),
        take_profit_levels=(Decimal("0.0012"),),
        trailing_stop=Decimal("0.00095"),
        atr=Decimal("0.00002"),
        risk_reward=Decimal("2"),
        size_usdt=Decimal("10"),
        validation_status=ValidationStatus.LIVE_ELIGIBLE,
        execution_allowed=True,
    )

    assert signal.execution_allowed is True


def test_price_zone_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="lower cannot exceed"):
        PriceZone(Decimal("2"), Decimal("1"))


def test_agent_score_rejects_empty_name_and_invalid_value() -> None:
    with pytest.raises(ValueError, match="agent_name"):
        AgentScore(" ", 50.0)
    with pytest.raises(ValueError, match="between 0 and 100"):
        AgentScore("trend", 101.0)


def test_price_zone_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        PriceZone(Decimal("-1"), Decimal("1"))


def test_signal_rejects_empty_identity_and_reason_codes() -> None:
    with pytest.raises(ValueError, match="snapshot_id and trade_id"):
        Signal(symbol="HOTUSDT", timeframes=("1h",), snapshot_id="")
    with pytest.raises(ValueError, match="reason_codes"):
        Signal(symbol="HOTUSDT", timeframes=("1h",), reason_codes=())


def build_executable_signal() -> Signal:
    return Signal(
        symbol="HOTUSDT",
        timeframes=("1h",),
        timestamp=NOW,
        snapshot_id="snapshot-1",
        trade_id="trade-1",
        latest_price=Decimal("1"),
        action=Action.BUY,
        decision_state=Decision.BUY,
        setup_tier=SetupTier.A,
        final_signal_score=80.0,
        entry_zone=PriceZone(Decimal("0.99"), Decimal("1")),
        invalidation_level=Decimal("0.89"),
        stop_loss=Decimal("0.9"),
        take_profit_levels=(Decimal("1.2"),),
        trailing_stop=Decimal("0.95"),
        atr=Decimal("0.02"),
        risk_reward=Decimal("2"),
        size_usdt=Decimal("10"),
        validation_status=ValidationStatus.LIVE_ELIGIBLE,
        execution_allowed=True,
    )


NOW = datetime(2026, 7, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda signal: replace(
                signal,
                action=Action.HOLD,
                decision_state=Decision.MARKET,
            ),
            "only BUY or inventory SELL",
        ),
        (
            lambda signal: replace(signal, decision_state=Decision.PAPER_ONLY),
            "decision_state cannot allow execution",
        ),
        (
            lambda signal: replace(
                signal,
                setup_tier=SetupTier.B,
                final_signal_score=75.0,
            ),
            r"only A\* or A",
        ),
        (
            lambda signal: replace(
                signal,
                validation_status=ValidationStatus.PAPER_APPROVED,
            ),
            "LIVE_ELIGIBLE",
        ),
        (
            lambda signal: replace(signal, blockers=("RISK_BLOCK",)),
            "while blockers exist",
        ),
    ],
)
def test_execution_rejects_invalid_authority_combinations(
    mutator: Callable[[Signal], Signal],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        mutator(build_executable_signal())


def test_signal_rejects_negative_numeric_values() -> None:
    with pytest.raises(ValueError, match="latest_price cannot be negative"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            latest_price=Decimal("-1"),
        )
    with pytest.raises(ValueError, match="take_profit_levels"):
        Signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            take_profit_levels=(Decimal("-1"),),
        )

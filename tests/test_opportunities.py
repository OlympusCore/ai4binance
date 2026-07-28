"""Research-only opportunity observation tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.domain import Action, SetupTier
from ai4binance.opportunities import (
    OpportunityBias,
    VWAPOpportunity,
    VWAPOpportunityConfig,
    VWAPOpportunityEvaluator,
)
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle, PromotionStatus

START = datetime(2026, 7, 11, tzinfo=UTC)


def snapshot(*, bearish: bool = False, latest_volume: str = "1000") -> MarketSnapshot:
    rows: list[OHLCVCandle] = []
    for index in range(21):
        close = Decimal("100")
        volume = Decimal("100")
        if index == 19:
            close = Decimal("101") if bearish else Decimal("99")
        if index == 20:
            close = Decimal("98") if bearish else Decimal("102")
            volume = Decimal(latest_volume)
        rows.append(
            OHLCVCandle(
                timestamp=START + timedelta(minutes=15 * index),
                open=Decimal("100"),
                high=max(Decimal("103"), close),
                low=min(Decimal("97"), close),
                close=close,
                volume=volume,
            )
        )
    return MarketSnapshot(
        snapshot_id="vwap-snapshot",
        created_at=rows[-1].timestamp,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": tuple(rows)},
        latest_price=rows[-1].close,
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_VALID,
    )


def evaluate(
    market: MarketSnapshot,
    *,
    structure_aligned: bool = True,
    htf_aligned: bool = True,
    inventory_available: bool = False,
) -> VWAPOpportunity:
    return VWAPOpportunityEvaluator().evaluate(
        market,
        timeframe="15m",
        session_start=START,
        structure_aligned=structure_aligned,
        htf_aligned=htf_aligned,
        inventory_available=inventory_available,
    )


def test_confirmed_bullish_reclaim_is_still_research_only() -> None:
    result = evaluate(snapshot())
    assert result.bias is OpportunityBias.BULLISH
    assert result.action is Action.BUY
    assert result.setup_tier is SetupTier.B
    assert result.blockers == ()
    assert result.promotion_status is PromotionStatus.RESEARCH_ONLY
    assert result.execution_allowed is False


def test_confirmation_failures_force_no_trade() -> None:
    result = evaluate(
        snapshot(latest_volume="100"),
        structure_aligned=False,
        htf_aligned=False,
    )
    assert result.action is Action.NO_TRADE
    assert "VOLUME_CONFIRMATION_MISSING" in result.blockers
    assert "STRUCTURE_CONFIRMATION_REQUIRED" in result.blockers
    assert "HTF_CONFIRMATION_REQUIRED" in result.blockers


def test_spot_sell_requires_inventory() -> None:
    blocked = evaluate(snapshot(bearish=True))
    allowed_observation = evaluate(snapshot(bearish=True), inventory_available=True)
    assert blocked.action is Action.NO_TRADE
    assert "SPOT_INVENTORY_REQUIRED_FOR_SELL" in blocked.blockers
    assert allowed_observation.action is Action.SELL
    assert allowed_observation.execution_allowed is False


def test_insufficient_session_data_fails_closed() -> None:
    result = VWAPOpportunityEvaluator().evaluate(
        snapshot(),
        timeframe="15m",
        session_start=START + timedelta(hours=4),
        structure_aligned=True,
        htf_aligned=True,
    )
    assert result.action is Action.NO_TRADE
    assert result.blockers == ("INSUFFICIENT_SESSION_DATA",)


def test_config_and_session_boundary_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        VWAPOpportunityConfig(atr_period=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        VWAPOpportunityEvaluator().evaluate(
            snapshot(),
            timeframe="15m",
            session_start=datetime(2026, 7, 11),
            structure_aligned=True,
            htf_aligned=True,
        )

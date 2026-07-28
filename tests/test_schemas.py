"""Shared snapshot and agent-state consistency tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    AnalysisState,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
    OOSValidationStatus,
    PromotionStatus,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def build_snapshot(snapshot_id: str = "snapshot-1") -> MarketSnapshot:
    candle = OHLCVCandle(
        timestamp=NOW,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("100"),
    )
    return MarketSnapshot(
        snapshot_id=snapshot_id,
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="hotusdt",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": [candle]},
        latest_price=Decimal("1.5"),
        bid=Decimal("1.49"),
        ask=Decimal("1.51"),
        spread=Decimal("0.02"),
        data_freshness={"1h": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
    )


def build_agent_result(snapshot_id: str = "snapshot-1") -> AgentResult:
    return AgentResult(
        agent_name="trend",
        agent_version="1.0.0",
        snapshot_id=snapshot_id,
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframes=("1h",),
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=0.5,
        score=75.0,
        confidence=0.7,
        reason_codes=("TREND_UP",),
    )


def test_snapshot_defensively_freezes_nested_input() -> None:
    freshness: dict[str, object] = {"1h": {"stale": False}}
    snapshot = MarketSnapshot(
        snapshot_id="snapshot-1",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={},
        latest_price=None,
        bid=None,
        ask=None,
        spread=None,
        data_freshness=freshness,
    )
    freshness["1h"] = {"stale": True}
    assert snapshot.data_freshness["1h"] != freshness["1h"]


def test_snapshot_rejects_crossed_market() -> None:
    with pytest.raises(ValueError, match="bid cannot exceed ask"):
        MarketSnapshot(
            snapshot_id="snapshot-1",
            created_at=NOW,
            exchange="Binance",
            market_type="Spot",
            symbol="HOTUSDT",
            timeframes=("1h",),
            ohlcv_by_timeframe={},
            latest_price=Decimal("1"),
            bid=Decimal("2"),
            ask=Decimal("1"),
            spread=Decimal("1"),
        )


def test_candle_rejects_invalid_values_and_relationships() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OHLCVCandle(
            timestamp=datetime(2026, 7, 11),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=Decimal("1"),
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        OHLCVCandle(
            NOW, Decimal("1"), Decimal("2"), Decimal("0.5"), Decimal("1"), Decimal("-1")
        )
    with pytest.raises(ValueError, match="invalid OHLC"):
        OHLCVCandle(
            NOW, Decimal("3"), Decimal("2"), Decimal("1"), Decimal("1.5"), Decimal("1")
        )
    with pytest.raises(ValueError, match="low cannot exceed"):
        OHLCVCandle(
            NOW, Decimal("2"), Decimal("1"), Decimal("2"), Decimal("2"), Decimal("1")
        )


def test_unvalidated_agent_cannot_be_hard_gate() -> None:
    with pytest.raises(ValueError, match="hard-gate"):
        AgentResult(
            agent_name="experimental",
            agent_version="0.1.0",
            snapshot_id="snapshot-1",
            timestamp=NOW,
            symbol="HOTUSDT",
            timeframes=("1h",),
            status=AgentStatus.SUCCESS,
            data_quality=DataQuality.DATA_VALID,
            applicable=True,
            directional_vote=0.0,
            score=50.0,
            confidence=0.5,
            hard_gate_eligible=True,
            promotion_status=PromotionStatus.RESEARCH_ONLY,
            reason_codes=("EXPERIMENTAL",),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("directional_vote", 2.0, "directional_vote"),
        ("score", 101.0, "score"),
        ("confidence", -0.1, "confidence"),
    ],
)
def test_agent_rejects_invalid_ranges(
    field: str,
    value: float,
    message: str,
) -> None:
    arguments: dict[str, object] = {
        "agent_name": "trend",
        "agent_version": "1.0.0",
        "snapshot_id": "snapshot-1",
        "timestamp": NOW,
        "symbol": "HOTUSDT",
        "timeframes": ("1h",),
        "status": AgentStatus.SUCCESS,
        "data_quality": DataQuality.DATA_VALID,
        "applicable": True,
        "directional_vote": 0.0,
        "score": 50.0,
        "confidence": 0.5,
        "reason_codes": ("TEST",),
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=message):
        AgentResult(**arguments)  # type: ignore[arg-type]


def test_validated_agent_may_be_hard_gate() -> None:
    result = build_agent_result()
    result = AgentResult(
        agent_name=result.agent_name,
        agent_version=result.agent_version,
        snapshot_id=result.snapshot_id,
        timestamp=result.timestamp,
        symbol=result.symbol,
        timeframes=result.timeframes,
        status=result.status,
        data_quality=result.data_quality,
        applicable=result.applicable,
        directional_vote=result.directional_vote,
        score=result.score,
        confidence=result.confidence,
        hard_gate_eligible=True,
        promotion_status=PromotionStatus.PAPER_APPROVED,
        oos_validation_status=OOSValidationStatus.APPROVED,
        reason_codes=("OOS_APPROVED",),
        calculation_metadata={"windows": {20, 50}},
    )
    assert result.hard_gate_eligible is True


def test_hard_gate_requires_approved_oos_evidence() -> None:
    result = build_agent_result()
    with pytest.raises(ValueError, match="approved OOS"):
        AgentResult(
            agent_name=result.agent_name,
            agent_version=result.agent_version,
            snapshot_id=result.snapshot_id,
            timestamp=result.timestamp,
            symbol=result.symbol,
            timeframes=result.timeframes,
            status=result.status,
            data_quality=result.data_quality,
            applicable=result.applicable,
            directional_vote=result.directional_vote,
            score=result.score,
            confidence=result.confidence,
            hard_gate_eligible=True,
            promotion_status=PromotionStatus.PAPER_APPROVED,
            reason_codes=("OOS_MISSING",),
        )


def test_analysis_state_accepts_matching_snapshot_results() -> None:
    state = AnalysisState(
        snapshot_id="snapshot-1",
        symbol="HOTUSDT",
        timestamp=NOW,
        market_snapshot=build_snapshot(),
        agent_results={"trend": build_agent_result()},
    )
    assert state.agent_results["trend"].score == 75.0


def test_analysis_state_rejects_mixed_snapshots() -> None:
    with pytest.raises(ValueError, match="every agent result"):
        AnalysisState(
            snapshot_id="snapshot-1",
            symbol="HOTUSDT",
            timestamp=NOW,
            market_snapshot=build_snapshot(),
            agent_results={"trend": build_agent_result("snapshot-2")},
        )


def test_analysis_state_rejects_state_snapshot_mismatch() -> None:
    with pytest.raises(ValueError, match="snapshot IDs"):
        AnalysisState(
            snapshot_id="snapshot-2",
            symbol="HOTUSDT",
            timestamp=NOW,
            market_snapshot=build_snapshot(),
        )


def test_analysis_state_rejects_symbol_mismatch() -> None:
    with pytest.raises(ValueError, match="snapshot symbols"):
        AnalysisState(
            snapshot_id="snapshot-1",
            symbol="BTCUSDT",
            timestamp=NOW,
            market_snapshot=build_snapshot(),
        )

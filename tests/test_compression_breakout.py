from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.domain import Action, ValidationStatus
from ai4binance.schemas import MarketSnapshot, OHLCVCandle
from ai4binance.strategies.compression import CompressionBreakoutPlaybookEngine
from tests.test_strategy_risk import agent_result, evidence, snapshot


def _compression_snapshot() -> MarketSnapshot:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[OHLCVCandle] = []
    for index in range(24):
        high = Decimal("11") if index in {4, 12} else Decimal("10.8")
        candles.append(
            OHLCVCandle(
                start + timedelta(hours=index),
                Decimal("10"),
                high,
                Decimal("9"),
                Decimal("10.2"),
                Decimal("100"),
            )
        )
    for index in range(8):
        candles.append(
            OHLCVCandle(
                start + timedelta(hours=24 + index),
                Decimal("10.40"),
                Decimal("10.55"),
                Decimal("10.30"),
                Decimal("10.45"),
                Decimal("90"),
            )
        )
    candles.extend(
        (
            OHLCVCandle(
                start + timedelta(hours=32),
                Decimal("10.5"),
                Decimal("11.8"),
                Decimal("10.4"),
                Decimal("11.5"),
                Decimal("180"),
            ),
            OHLCVCandle(
                start + timedelta(hours=33),
                Decimal("11.4"),
                Decimal("11.6"),
                Decimal("10.95"),
                Decimal("11.3"),
                Decimal("120"),
            ),
        )
    )
    return replace(
        snapshot(),
        created_at=start + timedelta(hours=34),
        ohlcv_by_timeframe={"1h": tuple(candles)},
        latest_price=Decimal("11.3"),
    )


def test_compression_breakout_generates_research_only_candidate() -> None:
    results = evidence(0.8)
    results["volatility"] = agent_result("volatility", 0.5)
    results["volume"] = agent_result("volume", 0.6)

    candidates = CompressionBreakoutPlaybookEngine().generate(
        _compression_snapshot(), results
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.setup_name == "compression_breakout"
    assert candidate.action is Action.BUY
    assert candidate.risk_reward == Decimal("2")
    assert candidate.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert candidate.blockers == ()


def test_compression_breakout_rejects_missing_volume_agent() -> None:
    assert (
        CompressionBreakoutPlaybookEngine().generate(
            _compression_snapshot(), evidence(0.8)
        )
        == ()
    )

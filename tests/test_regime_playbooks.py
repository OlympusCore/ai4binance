from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from test_strategy_risk import agent_result, evidence, snapshot

from ai4binance.domain import Action, ValidationStatus
from ai4binance.schemas import AgentResult, MarketSnapshot, OHLCVCandle
from ai4binance.strategies.regime_playbooks import (
    RegimePlaybookEngine,
    liquidity_sweep_reversal_evidence,
    range_rotation_evidence,
    volatility_expansion_evidence,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    index: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: str = "100",
) -> OHLCVCandle:
    return OHLCVCandle(
        START + timedelta(hours=index),
        Decimal(open_),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        Decimal(volume),
    )


def _range_candles() -> tuple[OHLCVCandle, ...]:
    candles = tuple(
        _candle(
            index,
            "10",
            "11" if index in {12, 25} else "10.4",
            "9" if index in {15, 27} else "9.6",
            "10",
        )
        for index in range(30)
    )
    return (*candles, _candle(30, "9.3", "9.5", "9", "9.4"))


def _expansion_candles() -> tuple[OHLCVCandle, ...]:
    candles = tuple(_candle(index, "10", "10.5", "9.5", "10") for index in range(30))
    return (*candles, _candle(30, "10", "12", "9.9", "11.8", "200"))


def _sweep_candles() -> tuple[OHLCVCandle, ...]:
    candles = tuple(_candle(index, "10", "10.5", "9", "10") for index in range(30))
    return (
        *candles,
        _candle(30, "9.2", "10", "8.3", "9.4", "180"),
        _candle(31, "9.5", "10.6", "9.4", "10.5", "150"),
    )


def _market(candles: tuple[OHLCVCandle, ...]) -> MarketSnapshot:
    return replace(
        snapshot(),
        created_at=candles[-1].timestamp + timedelta(hours=1),
        latest_price=candles[-1].close,
        ohlcv_by_timeframe={"1h": candles},
    )


def _agents() -> dict[str, AgentResult]:
    results = evidence(0.5)
    results["volatility"] = agent_result("volatility", 0.3)
    return results


def test_three_regime_evidence_rules_are_deterministic() -> None:
    assert range_rotation_evidence(_range_candles()) is not None
    assert volatility_expansion_evidence(_expansion_candles()) is not None
    assert liquidity_sweep_reversal_evidence(_sweep_candles()) is not None


def test_regime_engine_generates_research_only_buy_candidates() -> None:
    candidates = RegimePlaybookEngine().generate(_market(_sweep_candles()), _agents())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.setup_name == "smc_liquidity_sweep_reversal"
    assert candidate.action is Action.BUY
    assert candidate.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert candidate.blockers == ()


def test_regime_engine_rejects_missing_volatility_evidence() -> None:
    generated = RegimePlaybookEngine().generate(
        _market(_range_candles()), evidence(0.5)
    )
    assert generated == ()

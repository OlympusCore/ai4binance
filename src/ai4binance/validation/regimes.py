"""Canonical deterministic OHLCV regime classification for validation."""

from decimal import Decimal

from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.models import MarketRegime


def classify_validation_regime(candle: OHLCVCandle) -> MarketRegime:
    """Classify one closed candle without future or wallet state."""

    if candle.open > 0 and (candle.high - candle.low) / candle.open >= Decimal("0.03"):
        return MarketRegime.HIGH_VOLATILITY
    if candle.close > candle.open:
        return MarketRegime.TREND
    return MarketRegime.RANGE

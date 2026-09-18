"""Deterministic Binance timeframe duration mapping."""

from datetime import timedelta

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1s": 1,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}


def timeframe_duration(timeframe: str) -> timedelta:
    """Return a fixed freshness duration for a supported Binance interval."""
    try:
        seconds = _TIMEFRAME_SECONDS[timeframe]
    except KeyError:
        raise ValueError(f"unsupported timeframe: {timeframe}") from None
    return timedelta(seconds=seconds)

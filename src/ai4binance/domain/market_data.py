"""Immutable candle and out-of-sample validation contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class OOSValidationStatus(StrEnum):
    """Out-of-sample evidence state used for hard-gate governance."""

    UNVALIDATED = "UNVALIDATED"
    INSUFFICIENT = "INSUFFICIENT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _require_aware_timestamp(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OHLCVCandle:
    """Immutable market candle with basic integrity checks."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Reject impossible OHLC relationships and negative values."""
        _require_aware_timestamp("timestamp", self.timestamp)
        if min(self.open, self.high, self.low, self.close, self.volume) < Decimal("0"):
            raise ValueError("OHLCV values cannot be negative")
        if self.low > self.high:
            raise ValueError("candle low cannot exceed high")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("invalid OHLC relationship")

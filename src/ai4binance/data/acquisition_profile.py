"""Research acquisition windows and exact native-grid validation.

These targets do not amend strategy warmup, retention, or execution authority.
"""

import json
from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256

from ai4binance.data.market_history_continuous import ContinuousMarketHistory
from ai4binance.data.timeframes import timeframe_duration

PROFILE_ID = "TOP5_SPOT_1000_FUTURES_CALENDAR_MONTH_V1"
PROFILE_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
SAFE_STATE = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}


def content_digest(payload: object) -> str:
    """Hash the canonical decoded representation, not an exchange CHECKSUM."""
    return sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def completed_boundary(cutoff: datetime, timeframe: str) -> datetime:
    if cutoff.utcoffset() is None:
        raise ValueError("profile cutoff must be timezone-aware")
    seconds = int(timeframe_duration(timeframe).total_seconds())
    return datetime.fromtimestamp(int(cutoff.timestamp()) // seconds * seconds, UTC)


def previous_calendar_month(value: datetime) -> datetime:
    """Subtract one calendar month with explicit month-end clamping."""
    value = value.astimezone(UTC)
    year, month = (
        (value.year, value.month - 1) if value.month > 1 else (value.year - 1, 12)
    )
    return value.replace(
        year=year, month=month, day=min(value.day, monthrange(year, month)[1])
    )


@dataclass(frozen=True, slots=True)
class AcquisitionWindow:
    market: str
    timeframe: str
    start: datetime
    end: datetime
    expected_count: int


def acquisition_window(
    market: str, timeframe: str, cutoff: datetime
) -> AcquisitionWindow:
    if timeframe not in PROFILE_TIMEFRAMES or market not in {"spot", "usd_m_futures"}:
        raise ValueError("unsupported acquisition profile stream")
    duration = timeframe_duration(timeframe)
    end = completed_boundary(cutoff, timeframe)
    start = end - 1000 * duration if market == "spot" else previous_calendar_month(end)
    return AcquisitionWindow(
        market, timeframe, start, end, int((end - start) / duration)
    )


def validate_native_rows(
    rows: object, *, start: datetime, end: datetime, timeframe: str
) -> list[list[str]]:
    """Retain all twelve decimal/native fields after canonical candle checks."""
    if not isinstance(rows, list):
        raise ValueError("native kline response must be an array")
    duration = timeframe_duration(timeframe)
    ContinuousMarketHistory._parse_rows(rows, start, end, interval=duration)
    normalized = [[str(value) for value in row] for row in rows]
    for row in normalized:
        epoch = int(row[0])
        divisor = 1_000_000 if epoch >= 100_000_000_000_000 else 1000
        if epoch % (int(duration.total_seconds()) * divisor):
            raise ValueError("native kline open time is off the UTC grid")
    return normalized


def exact_quote_volume(
    rows: Sequence[Sequence[str]], start: datetime, end: datetime
) -> str:
    """Require exactly the complete 168-hour grid before summing quote notional."""
    if len(rows) != 168:
        raise ValueError("weekly ranking requires 168 closed native hourly bars")
    opens = [
        datetime.fromtimestamp(
            int(row[0]) / (1_000_000 if int(row[0]) >= 100_000_000_000_000 else 1000),
            UTC,
        )
        for row in rows
    ]
    if opens != [
        start + timedelta(hours=index) for index in range(168)
    ] or end != start + timedelta(hours=168):
        raise ValueError("weekly ranking grid is incomplete")
    return sum_decimal_strings([row[7] for row in rows])


def sum_decimal_strings(values: Sequence[str]) -> str:
    """Keep sums exact within a bounded native decimal representation."""
    numbers = [Decimal(value) for value in values]
    if any(
        not number.is_finite()
        or len(number.as_tuple().digits) > 128
        or abs(int(number.as_tuple().exponent)) > 128
        for number in numbers
    ):
        raise ValueError("native decimal exceeds exact representation bounds")
    with localcontext() as context:
        context.prec = 512
        return str(sum(numbers, Decimal(0)))


def stream_health(
    window: AcquisitionWindow,
    timestamps: Sequence[datetime],
    *,
    strategy_required_bars: int,
    verified_archive_count: int,
    lineage: Mapping[str, object],
    warmup_verified: bool = False,
) -> dict[str, object]:
    duration = timeframe_duration(window.timeframe)
    expected = {
        window.start + index * duration for index in range(window.expected_count)
    }
    actual = set(timestamps)
    missing = sorted(expected - actual)
    duplicate_count = len(timestamps) - len(actual)
    valid = not missing and not duplicate_count and actual <= expected
    return {
        "market": window.market,
        "timeframe": window.timeframe,
        "requested_start": window.start.isoformat(),
        "requested_end_exclusive": window.end.isoformat(),
        "requested_bars": window.expected_count,
        "available_verified_bars": len(actual & expected),
        "missing_count": len(missing),
        "coverage_ratio": str(
            Decimal(len(actual & expected)) / Decimal(window.expected_count)
        ),
        "missing_open_times": [value.isoformat() for value in missing],
        "duplicate_count": duplicate_count,
        "last_closed_open": max(actual).isoformat() if actual else None,
        "actual_start": min(actual).isoformat() if actual else None,
        "actual_end_exclusive": (max(actual) + duration).isoformat()
        if actual
        else None,
        "source_lag_seconds": max(
            0, int((window.end - max(actual) - duration).total_seconds())
        )
        if actual
        else None,
        "expected_latest_closed_open": (window.end - duration).isoformat(),
        "tail_ready": window.end - duration in actual,
        "strategy_required_bars": strategy_required_bars,
        "verified_archive_count": verified_archive_count,
        "warmup_ready": warmup_verified,
        "warmup_grid_status": "VERIFIED" if warmup_verified else "NOT_READY",
        "warmup_blockers": [] if warmup_verified else ["WARMUP_INSUFFICIENT"],
        "status": "DATA_READY_1000"
        if valid and window.market == "spot"
        else "DATA_READY_MONTH"
        if valid
        else "PARTIAL",
        "source_lineage": dict(lineage),
        "analysis_status": "NOT_EVALUATED",
        **SAFE_STATE,
    }

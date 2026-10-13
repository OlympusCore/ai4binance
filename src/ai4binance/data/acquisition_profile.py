"""Research acquisition windows and exact native-grid validation.

These targets do not amend strategy warmup, retention, or execution authority.
"""

from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
from typing import cast

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import ContinuousMarketHistory
from ai4binance.data.timeframes import timeframe_duration

PROFILE_ID = "TOP5_SPOT_1000_FUTURES_CALENDAR_MONTH_V1"
PROFILE_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
SAFE_STATE = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
CANDLE_HEALTH_SCOPE = "SPOT_1000_CLOSED_BARS_FUTURES_30_DAYS"


def candle_health_window(
    market: str, timeframe: str, cutoff: datetime
) -> AcquisitionWindow:
    """Define candle health independently of ranking and strategy warmup."""
    if market not in {"spot", "usd_m_futures"} or timeframe not in PROFILE_TIMEFRAMES:
        raise ValueError("unsupported candle health stream")
    duration = timeframe_duration(timeframe)
    end = completed_boundary(cutoff, timeframe)
    start = end - (1000 * duration if market == "spot" else timedelta(days=30))
    return AcquisitionWindow(
        market, timeframe, start, end, int((end - start) / duration)
    )


def _verified_candle_health_stream(
    archive_root: Path, market: str, symbol: str, timeframe: str, cutoff: datetime
) -> dict[str, object]:
    window = candle_health_window(market, timeframe, cutoff)
    archive = ParquetOHLCVArchive(archive_root / market)
    lineage: dict[str, object] = {}
    timestamps: list[datetime] = []
    error_code = None
    try:
        manifest = archive.manifest(symbol, timeframe)
        if (
            manifest.symbol != symbol
            or manifest.timeframe != timeframe
            or not manifest.source.startswith(
                ("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")
            )
        ):
            raise ValueError("candle health source identity is invalid")
        candles = archive.read_window(
            symbol,
            timeframe,
            start_at=window.start,
            end_at=window.end - timeframe_duration(timeframe),
        )
        if archive.manifest(symbol, timeframe) != manifest:
            raise ValueError("candle health archive changed during verification")
        timestamps = [candle.timestamp for candle in candles]
        lineage = {"source": manifest.source, "dataset_sha256": manifest.sha256}
    except (OSError, ValueError, ArithmeticError) as error:
        error_code = type(error).__name__
    row = stream_health(
        window,
        timestamps,
        strategy_required_bars=200,
        verified_archive_count=len(timestamps),
        lineage=lineage,
    )
    for field in (
        "strategy_required_bars",
        "warmup_ready",
        "warmup_grid_status",
        "warmup_blockers",
        "analysis_status",
    ):
        row.pop(field)
    missing = row.pop("missing_open_times")
    row.update(
        symbol=symbol,
        status="VERIFIED" if str(row["status"]).startswith("DATA_READY") else "PARTIAL",
        missing_open_time_sample=cast(list[str], missing)[:5],
        error_code=error_code,
    )
    return row


def candle_window_health(
    archive_root: Path,
    *,
    symbols: Mapping[str, Sequence[str]],
    cutoff: datetime,
    universe_blockers: Sequence[str] = (),
) -> dict[str, object]:
    """Verify current native OHLCV windows using the canonical archive reader.

    This evidence grants no strategy, enrichment, retention or execution authority.
    """
    rows = [
        _verified_candle_health_stream(archive_root, market, symbol, timeframe, cutoff)
        for market in ("spot", "usd_m_futures")
        for symbol in symbols.get(market, ())
        for timeframe in PROFILE_TIMEFRAMES
    ]
    blockers = list(universe_blockers)
    if not rows:
        blockers.append("CANDLE_HEALTH_UNIVERSE_EMPTY")
    if any(row["status"] != "VERIFIED" for row in rows):
        blockers.append("REQUIRED_NATIVE_CANDLE_WINDOW_INCOMPLETE")
    return {
        "schema_version": 1,
        "scope": CANDLE_HEALTH_SCOPE,
        "status": "PARTIAL" if blockers else "VERIFIED",
        "observed_at": cutoff.astimezone(UTC).isoformat(),
        "symbols": {
            market: list(symbols.get(market, ()))
            for market in ("spot", "usd_m_futures")
        },
        "timeframes": list(PROFILE_TIMEFRAMES),
        "spot_required_bars": 1000,
        "futures_required_days": 30,
        "stream_count": len(rows),
        "verified_stream_count": sum(row["status"] == "VERIFIED" for row in rows),
        "streams": rows,
        "blockers": sorted(set(blockers)),
        "analysis_status": "NOT_EVALUATED",
        **SAFE_STATE,
    }


def _current_candle_health_stream(row: Mapping[str, object], now: datetime) -> bool:
    try:
        window = candle_health_window(str(row["market"]), str(row["timeframe"]), now)
        lineage = row["source_lineage"]
        digest = (
            str(lineage.get("dataset_sha256", ""))
            if isinstance(lineage, Mapping)
            else ""
        )
        return (
            row["status"] == "VERIFIED"
            and type(row["requested_bars"]) is int
            and row["requested_bars"] == window.expected_count
            and type(row["available_verified_bars"]) is int
            and row["available_verified_bars"] == window.expected_count
            and row["missing_count"] == 0
            and row["duplicate_count"] == 0
            and type(row["missing_count"]) is int
            and type(row["duplicate_count"]) is int
            and row["tail_ready"] is True
            and datetime.fromisoformat(str(row["requested_start"])) == window.start
            and datetime.fromisoformat(str(row["requested_end_exclusive"]))
            == window.end
            and datetime.fromisoformat(str(row["last_closed_open"]))
            == window.end - timeframe_duration(window.timeframe)
            and isinstance(lineage, Mapping)
            and str(lineage.get("source", "")).startswith(
                ("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")
            )
            and len(digest) == 64
            and all(char in "0123456789abcdef" for char in digest)
        )
    except KeyError, TypeError, ValueError:
        return False


def candle_health_status(report: object, now: datetime) -> str:
    """Reject expired or inconsistent candle proofs independently of heartbeats."""
    if not isinstance(report, Mapping) or report.get("scope") != CANDLE_HEALTH_SCOPE:
        return "NOT_VERIFIED"
    if (
        report.get("status") != "VERIFIED"
        or report.get("blockers") != []
        or report.get("execution_allowed") is not False
        or report.get("promotion_status") != "RESEARCH_ONLY"
        or report.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        return "PARTIAL"
    try:
        declared = report["symbols"]
        rows = report["streams"]
        if not isinstance(declared, Mapping) or not isinstance(rows, list):
            return "NOT_VERIFIED"
        expected = _candle_health_identities(declared)
        actual = {(row["market"], row["symbol"], row["timeframe"]) for row in rows}
        observed = datetime.fromisoformat(str(report["observed_at"]))
        if (
            not expected
            or actual != expected
            or len(rows) != len(expected)
            or report.get("stream_count") != len(expected)
            or report.get("verified_stream_count") != len(expected)
            or not 0 <= (now - observed).total_seconds() < 300
        ):
            return "NOT_VERIFIED"
        return (
            "VERIFIED"
            if all(_current_candle_health_stream(row, now) for row in rows)
            else "STALE"
        )
    except KeyError, TypeError, ValueError:
        return "NOT_VERIFIED"


def _candle_health_identities(
    declared: Mapping[str, object],
) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()
    for market in ("spot", "usd_m_futures"):
        symbols = declared[market]
        if not isinstance(symbols, list) or len(symbols) > 100:
            raise ValueError("candle health symbols are invalid")
        for symbol in symbols:
            if not isinstance(
                symbol, str
            ) or symbol != ParquetOHLCVArchive._validate_identity(
                symbol, "1d", "health"
            ):
                raise ValueError("candle health identity is invalid")
            identities.update(
                (market, symbol, timeframe) for timeframe in PROFILE_TIMEFRAMES
            )
    return identities


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


def native_schedule(
    cutoff: datetime, timeframe: str, *, arrival_grace_seconds: int
) -> dict[str, object]:
    """Keep the expected boundary visible while delaying its acquisition deadline."""
    if isinstance(arrival_grace_seconds, bool) or not 0 <= arrival_grace_seconds <= 120:
        raise ValueError("source arrival grace must be between 0 and 120 seconds")
    boundary = completed_boundary(cutoff, timeframe)
    grace = timedelta(seconds=arrival_grace_seconds)
    return {
        "expected_closed_boundary": boundary.isoformat(),
        "source_arrival_grace_seconds": arrival_grace_seconds,
        "arrival_deadline": (boundary + grace).isoformat(),
        "next_native_due_at": (
            boundary + timeframe_duration(timeframe) + grace
        ).isoformat(),
        "acquisition_closed_boundary": completed_boundary(
            cutoff - grace, timeframe
        ).isoformat(),
    }


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

"""Artifact-producing integrity scans across governed indicators and strategies."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.indicators import (
    atr,
    closes,
    ema,
    ohlc4,
    relative_volume,
    rsi,
    session_vwap,
    supertrend,
)
from ai4binance.reporting import to_primitive
from ai4binance.schemas import OHLCVCandle
from ai4binance.strategies.rules import historical_playbook_trigger
from ai4binance.validation.integrity import (
    IndicatorFunction,
    IntegrityStatus,
    analyze_indicator_integrity,
)


@dataclass(frozen=True, slots=True)
class IntegrityTarget:
    name: str
    family: str
    compute: IndicatorFunction
    minimum_history: int

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.family.strip() or self.minimum_history < 2:
            raise ValueError("integrity target identity and history are required")


@dataclass(frozen=True, slots=True)
class IntegrityArtifactEntry:
    target: str
    family: str
    timeframe: str
    status: IntegrityStatus
    checked_points: int
    maximum_drift: float
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntegrityScanArtifact:
    artifact_id: str
    symbol: str
    created_at: datetime
    dataset_revision_id: str
    entries: tuple[IntegrityArtifactEntry, ...]
    sampled: bool
    blockers: tuple[str, ...]
    promotion_allowed: bool
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id.startswith("integrity:") or not self.entries:
            raise ValueError("integrity artifact identity and entries are required")
        if self.execution_allowed or self.promotion_allowed == bool(self.blockers):
            raise ValueError("integrity artifact must fail closed")


@dataclass(frozen=True, slots=True)
class IntegrityArtifactScanner:
    """Run every registered target and persist a bounded auditable artifact."""

    maximum_candles_per_timeframe: int | None = 128

    def scan(
        self,
        *,
        symbol: str,
        dataset_revision_id: str,
        candles_by_timeframe: Mapping[str, tuple[OHLCVCandle, ...]],
        targets: tuple[IntegrityTarget, ...] | None = None,
        created_at: datetime | None = None,
    ) -> IntegrityScanArtifact:
        selected = targets or default_integrity_targets()
        if not candles_by_timeframe or not selected:
            raise ValueError("integrity scan requires candles and targets")
        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("integrity artifact timestamp must be timezone-aware")
        sampled = False
        entries: list[IntegrityArtifactEntry] = []
        for timeframe in sorted(candles_by_timeframe):
            complete = candles_by_timeframe[timeframe]
            sample = complete
            if (
                self.maximum_candles_per_timeframe is not None
                and len(complete) > self.maximum_candles_per_timeframe
            ):
                sample = complete[-self.maximum_candles_per_timeframe :]
                sampled = True
            for target in selected:
                if len(sample) < target.minimum_history + 3:
                    entries.append(
                        IntegrityArtifactEntry(
                            target.name,
                            target.family,
                            timeframe,
                            IntegrityStatus.BLOCKED,
                            0,
                            0.0,
                            ("INTEGRITY_HISTORY_INSUFFICIENT",),
                        )
                    )
                    continue
                suite = analyze_indicator_integrity(
                    sample,
                    target.compute,
                    minimum_history=target.minimum_history,
                    warmup_offsets=(0, 1, 2),
                )
                entries.append(
                    IntegrityArtifactEntry(
                        target.name,
                        target.family,
                        timeframe,
                        suite.status,
                        suite.lookahead.checked_points,
                        max(
                            suite.lookahead.maximum_drift,
                            suite.recursive_stability.maximum_drift,
                        ),
                        suite.blockers,
                    )
                )
        blockers = [
            f"{item.timeframe}:{item.target}:{blocker}"
            for item in entries
            for blocker in item.blockers
        ]
        if sampled:
            blockers.append("BOUNDED_INTEGRITY_SCAN_ONLY")
        unique_blockers = tuple(dict.fromkeys(blockers))
        identity = _artifact_id(symbol, dataset_revision_id, tuple(entries))
        return IntegrityScanArtifact(
            artifact_id=identity,
            symbol=symbol.strip().upper(),
            created_at=timestamp,
            dataset_revision_id=dataset_revision_id,
            entries=tuple(entries),
            sampled=sampled,
            blockers=unique_blockers,
            promotion_allowed=not unique_blockers,
        )

    @staticmethod
    def write(artifact: IntegrityScanArtifact, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(to_primitive(artifact), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)


def default_integrity_targets() -> tuple[IntegrityTarget, ...]:
    """Return governed numeric indicator and implemented strategy targets."""
    indicators = (
        IntegrityTarget("ohlc4", "INDICATOR", _ohlc4_series, 2),
        IntegrityTarget("ema_8", "INDICATOR", _scalar_series(8, _ema_value), 8),
        IntegrityTarget("ema_21", "INDICATOR", _scalar_series(21, _ema_value), 21),
        IntegrityTarget("atr_14", "INDICATOR", _scalar_series(15, _atr_value), 15),
        IntegrityTarget("rsi_14", "INDICATOR", _scalar_series(15, _rsi_value), 15),
        IntegrityTarget(
            "relative_volume_20",
            "INDICATOR",
            _scalar_series(21, _relative_volume_value),
            21,
        ),
        IntegrityTarget("supertrend_band", "INDICATOR", _supertrend_band, 15),
        IntegrityTarget("supertrend_direction", "INDICATOR", _supertrend_direction, 15),
        IntegrityTarget("session_vwap", "INDICATOR", _session_vwap_series, 2),
    )
    strategies = tuple(
        IntegrityTarget(
            playbook,
            "STRATEGY",
            _strategy_series(playbook),
            22,
        )
        for playbook in (
            "trend_continuation",
            "pullback_continuation",
            "breakout_retest",
            "support_reclaim",
            "resistance_rejection",
            "failed_breakout_reversal",
            "compression_breakout",
        )
    )
    return (*indicators, *strategies)


def _scalar_series(
    minimum: int,
    value_fn: ValueFunction,
) -> IndicatorFunction:
    def compute(candles: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        return tuple(
            None if index + 1 < minimum else value_fn(candles[: index + 1], minimum)
            for index in range(len(candles))
        )

    return compute


ValueFunction = Callable[[tuple[OHLCVCandle, ...], int], float]


def _ema_value(candles: tuple[OHLCVCandle, ...], minimum: int) -> float:
    return float(ema(closes(candles), minimum))


def _atr_value(candles: tuple[OHLCVCandle, ...], minimum: int) -> float:
    return float(atr(candles, minimum - 1))


def _rsi_value(candles: tuple[OHLCVCandle, ...], minimum: int) -> float:
    return float(rsi(closes(candles), minimum - 1))


def _relative_volume_value(candles: tuple[OHLCVCandle, ...], minimum: int) -> float:
    return float(relative_volume(candles, minimum - 1))


def _ohlc4_series(candles: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
    return tuple(float(ohlc4(candle)) for candle in candles)


def _supertrend_band(candles: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
    output: list[float | None] = [None] * min(14, len(candles))
    if len(candles) >= 15:
        output.extend(float(point.band) for point in supertrend(candles, 14))
    return tuple(output)


def _supertrend_direction(
    candles: tuple[OHLCVCandle, ...],
) -> tuple[float | None, ...]:
    output: list[float | None] = [None] * min(14, len(candles))
    if len(candles) >= 15:
        output.extend(float(point.direction) for point in supertrend(candles, 14))
    return tuple(output)


def _session_vwap_series(
    candles: tuple[OHLCVCandle, ...],
) -> tuple[float | None, ...]:
    start = candles[0].timestamp
    return tuple(
        float(session_vwap(candles[: index + 1], start))
        for index in range(len(candles))
    )


def _strategy_series(playbook: str) -> IndicatorFunction:
    def compute(candles: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        return tuple(
            None
            if index + 1 < 22
            else float(historical_playbook_trigger(playbook, candles[: index + 1]))
            for index in range(len(candles))
        )

    return compute


def _artifact_id(
    symbol: str,
    revision_id: str,
    entries: tuple[IntegrityArtifactEntry, ...],
) -> str:
    from hashlib import sha256

    payload = "|".join(
        (
            symbol.strip().upper(),
            revision_id,
            *(f"{item.timeframe}:{item.target}:{item.status}" for item in entries),
        )
    )
    return f"integrity:{sha256(payload.encode('utf-8')).hexdigest()[:24]}"

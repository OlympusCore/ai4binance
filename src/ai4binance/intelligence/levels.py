"""Canonical structural-level map projected from existing level evidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.indicators import atr
from ai4binance.intelligence.contracts import (
    ConfirmedSwing,
    StructuralLevelEvidence,
    SwingKind,
    TimeframeStructureEvidence,
)
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    OHLCVCandle,
    is_usable_agent_result,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class StructuralLevelMapEngine:
    """Enrich the existing support/resistance owner into shared zones."""

    atr_zone_ratio: Decimal = Decimal("0.15")
    touch_lookback: int = 50

    def __post_init__(self) -> None:
        if self.atr_zone_ratio <= ZERO:
            raise ValueError("level-map ATR zone ratio must be positive")
        if self.touch_lookback < 14:
            raise ValueError("level-map touch lookback must be at least 14")

    def build(
        self,
        snapshot: MarketSnapshot,
        structures: tuple[TimeframeStructureEvidence, ...],
        result: AgentResult | None,
    ) -> tuple[StructuralLevelEvidence, ...]:
        """Build one reusable level map without owning primary direction."""
        if (
            result is None
            or not is_usable_agent_result(result)
            or result.blockers
            or result.snapshot_id != snapshot.snapshot_id
            or result.symbol != snapshot.symbol
            or result.timestamp != snapshot.created_at
            or result.agent_name != "support_resistance"
        ):
            return ()
        raw_timeframes = self._mapping(result.calculation_metadata.get("timeframes"))
        structure_by_timeframe = {item.timeframe: item for item in structures}
        levels: list[StructuralLevelEvidence] = []
        for timeframe in snapshot.timeframes:
            candles = tuple(
                c
                for c in snapshot.ohlcv_by_timeframe.get(timeframe, ())
                if c.timestamp + timeframe_duration(timeframe) <= snapshot.created_at
            )
            raw = self._mapping(raw_timeframes.get(timeframe))
            if len(candles) < 15 or not raw:
                continue
            volatility = atr(candles, 14)
            half_width = volatility * self.atr_zone_ratio
            structure = structure_by_timeframe.get(timeframe)
            if structure is not None and structure.swings:
                clusters = self._clusters(
                    structure.swings, snapshot.created_at, half_width
                )
                for kind, center, anchor, available_at in clusters[-20:]:
                    levels.append(
                        self._level(
                            snapshot,
                            timeframe,
                            kind,
                            center,
                            half_width,
                            candles,
                            result.confidence,
                            structure,
                            anchor,
                            available_at,
                        )
                    )
                if clusters:
                    continue
            for level_type in ("support", "resistance"):
                rolling_center = self._decimal(raw.get(level_type))
                if rolling_center is None or rolling_center <= ZERO:
                    continue
                levels.append(
                    self._level(
                        snapshot,
                        timeframe,
                        level_type,
                        rolling_center,
                        half_width,
                        candles,
                        result.confidence,
                        structure,
                    )
                )
        return tuple(levels)

    @staticmethod
    def _clusters(
        swings: tuple[ConfirmedSwing, ...],
        as_of: datetime,
        half_width: Decimal,
    ) -> list[tuple[str, Decimal, str, datetime]]:
        clusters: list[tuple[str, Decimal, str, datetime]] = []
        for swing in swings:
            if swing.available_at > as_of:
                continue
            kind = "support" if swing.kind is SwingKind.LOW else "resistance"
            if not any(
                k == kind and abs(center - swing.price) <= half_width * 2
                for k, center, _, _ in clusters
            ):
                clusters.append(
                    (
                        kind,
                        swing.price,
                        swing.occurred_at.isoformat(),
                        swing.available_at,
                    )
                )
        return clusters

    def _level(
        self,
        snapshot: MarketSnapshot,
        timeframe: str,
        level_type: str,
        center: Decimal,
        half_width: Decimal,
        candles: tuple[OHLCVCandle, ...],
        source_confidence: float,
        structure: TimeframeStructureEvidence | None,
        anchor: str = "rolling",
        available_at: datetime | None = None,
    ) -> StructuralLevelEvidence:
        typed_candles = tuple(
            c
            for c in candles[-self.touch_lookback :]
            if available_at is None or c.timestamp >= available_at
        )
        price_low = max(Decimal("0.00000001"), center - half_width)
        price_high = center + half_width
        contact_bars = tuple(
            index
            for index, candle in enumerate(typed_candles)
            if candle.low <= price_high and candle.high >= price_low
        )
        touches = tuple(
            index for index in contact_bars if index - 1 not in contact_bars
        )
        breached = tuple(
            candle.close < price_low
            if level_type == "support"
            else candle.close > price_high
            for candle in typed_candles
        )
        breaks = sum(
            current and index > 0 and not breached[index - 1]
            for index, current in enumerate(breached)
        )
        age_bars = (
            len(typed_candles) - 1 - contact_bars[-1]
            if contact_bars
            else len(typed_candles)
        )
        freshness = "FRESH" if age_bars <= 5 else "AGING" if age_bars <= 20 else "STALE"
        volatility = atr(candles, 14)
        reactions = (
            tuple(
                max(
                    ZERO,
                    max(
                        (
                            c.close - price_high
                            if level_type == "support"
                            else price_low - c.close
                        )
                        for c in typed_candles[
                            index : min(index + 4, len(typed_candles))
                        ]
                    ),
                )
                / volatility
                for index in touches
            )
            if volatility > ZERO
            else ()
        )
        rejection_strength = (
            float(min(Decimal("1"), sum(reactions, ZERO) / Decimal(len(reactions))))
            if reactions
            else 0.0
        )
        structure_confidence = structure.confidence if structure is not None else 1.0
        confidence = min(source_confidence, structure_confidence)
        latest_close = candles[-1].close
        role_flip = breaks > 0 and (
            (level_type == "support" and latest_close < price_low)
            or (level_type == "resistance" and latest_close > price_high)
        )
        identity = (
            f"{snapshot.market_type}|{snapshot.symbol}|{timeframe}|"
            f"{level_type}|{anchor}|{center}"
        )
        average_volume = sum((c.volume for c in typed_candles), ZERO) / Decimal(
            max(1, len(typed_candles))
        )
        contact_volume = (
            (
                sum((typed_candles[i].volume for i in touches), ZERO)
                / Decimal(len(touches))
            )
            if touches
            else ZERO
        )
        return StructuralLevelEvidence(
            level_id="level:" + sha256(identity.encode()).hexdigest()[:20],
            level_type=level_type.upper(),
            price_low=price_low,
            price_high=price_high,
            source_timeframe=timeframe,
            touch_count=len(touches),
            break_count=breaks,
            freshness=freshness,
            role_flip=role_flip,
            confidence=confidence,
            evidence_ref=f"support_resistance:{timeframe}:{level_type}",
            rejection_strength=rejection_strength,
            volume_context=(
                "ABOVE_WINDOW_AVERAGE"
                if contact_volume > average_volume
                else "AT_OR_BELOW_WINDOW_AVERAGE"
            )
            if touches
            else "NO_TOUCH",
            age_bars=age_bars,
        )

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            return {}
        return {str(key): item for key, item in value.items()}

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
